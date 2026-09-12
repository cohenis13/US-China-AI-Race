#!/usr/bin/env python3
"""
Fetch talent data and build the talent pipeline index.

THREE PROXIES
  1. Research Output Quality (weight 0.35) — OpenAlex API (auto-fetched)
     Three sub-signals combined:
       a) Paper volume (12m window, 30% within proxy)
          Raw count of AI/ML/NLP/CV papers by country of institution.
          China leads heavily on volume (~64%).
       b) High-impact papers (3y window, cited_by_count ≥ 50, 40% within proxy)
          Filters to papers with substantial citation traction.
          US leads here (~54%).
       c) Top-cited papers (2y window, cited_by_count ≥ 25, 30% within proxy)
          Intermediate quality filter.
          US slight lead (~52%).
     Together these balance raw volume against citation quality.

  2. Domestic Talent Pipeline (weight 0.25) — talent_manual.json
     Annual AI/CS PhD graduates at domestic universities.
     Measures long-run production capacity of each country's university system.
     China produces ~4× more AI-adjacent PhDs than the US.
     Data: NSF SDR 2022 (US), China MoE 2022 (China).

  3. Elite Researcher Concentration + Migration (weight 0.40) — talent_manual.json
     Where the world's top AI researchers actually work.
     Source: MacroPolo AI Talent Tracker 2023 (top 2,000 AI researchers by citation
     count at NeurIPS/ICML/ICLR).
     US institutions hold ~72% of the US+China top-researcher share.
     Key dynamic: US captures China-born elite talent — ~36% of China-undergraduate
     researchers in the global top-tier work at US institutions.

COMPOSITE
  share_score = proxy_us / (proxy_us + proxy_cn) × 100
  composite   = sum(weight_i × share_score_i)
  US + China composite always sums to 100.

INTERPRETATION
  Raw paper volume alone overstates China's talent advantage.
  Elite researcher concentration alone understates China's pipeline strength.
  The composite gives a more complete picture: ~50/50 near-tie, with small US
  advantage from elite capture, partially offset by China's larger pipeline.

Outputs to data/talent.json.

Usage:
    pip install requests
    python scripts/fetch_talent.py
"""

import json
import sys
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Run: pip install requests")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parent.parent
OUTPUT_FILE  = ROOT / "data" / "talent.json"
MANUAL_FILE  = ROOT / "data" / "talent_manual.json"

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_RESEARCH_OUTPUT = 0.35
WEIGHT_PIPELINE        = 0.25
WEIGHT_ELITE_MIGRATION = 0.40

# Sub-weights within research_output
SUB_WEIGHT_VOLUME     = 0.30
SUB_WEIGHT_HIGH_IMPACT = 0.40
SUB_WEIGHT_TOP_CITED   = 0.30

# ── OpenAlex config ───────────────────────────────────────────────────────────
OPENALEX_BASE    = "https://api.openalex.org/works"
REQUEST_TIMEOUT  = 30
RATE_LIMIT_SLEEP = 1.2
MAX_PAPERS_TABLE = 10

# OpenAlex concept IDs — stable identifiers for AI/ML/NLP/CV topics
CONCEPTS = "C154945302|C119857082|C204321447|C31972630"
# C154945302 = Artificial Intelligence
# C119857082 = Machine Learning
# C204321447 = Natural Language Processing
# C31972630  = Computer Vision

MAILTO = "ai-tracker@github-actions"

US_CODE = "US"
CN_CODE = "CN"


# ── Manual data ───────────────────────────────────────────────────────────────

def load_manual_data() -> dict:
    if not MANUAL_FILE.exists():
        log.error("talent_manual.json not found at %s", MANUAL_FILE)
        sys.exit(1)
    with open(MANUAL_FILE, encoding="utf-8") as f:
        data = json.load(f)
    log.info("Loaded talent_manual.json (last_updated: %s)", data.get("last_updated", "?"))
    return data


# ── OpenAlex helpers ──────────────────────────────────────────────────────────

def openalex_get(params: dict) -> dict | None:
    headers = {"User-Agent": f"ai-race-tracker/1.0 (mailto:{MAILTO})"}
    try:
        resp = requests.get(OPENALEX_BASE, params=params, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        log.warning("OpenAlex request failed: %s", e)
        return None


def fetch_country_breakdown(filter_str: str, label: str = "") -> tuple[dict, int]:
    """
    Fetch paper counts grouped by institution country code.
    Returns (breakdown dict, total_papers int).
    """
    params = {
        "filter":   filter_str,
        "group_by": "authorships.institutions.country_code",
        "per_page": 200,
        "mailto":   MAILTO,
    }
    data = openalex_get(params)
    if data is None:
        return {}, 0

    total_papers = data.get("meta", {}).get("count", 0)
    breakdown: dict[str | None, int] = {}
    for group in data.get("group_by", []):
        raw_key = group.get("key")
        count   = group.get("count", 0)
        key = raw_key.split("/")[-1] if raw_key else None
        breakdown[key] = count

    log.info("  %s: %d total papers, %d country groups", label, total_papers, len(breakdown))
    return breakdown, total_papers


def extract_us_cn(breakdown: dict) -> tuple[int, int]:
    return breakdown.get(US_CODE, 0), breakdown.get(CN_CODE, 0)


def fetch_recent_papers(filter_str: str, n: int = MAX_PAPERS_TABLE) -> list[dict]:
    params = {
        "filter":   filter_str,
        "sort":     "publication_date:desc",
        "per_page": n,
        "select":   "id,title,publication_date,authorships,cited_by_count",
        "mailto":   MAILTO,
    }
    data = openalex_get(params)
    if data is None:
        return []

    papers = []
    for p in data.get("results", []):
        authors:   list[str] = []
        countries: list[str] = []
        for auth in p.get("authorships", []):
            name = (auth.get("author") or {}).get("display_name", "")
            if name:
                authors.append(name)
            for code in auth.get("countries", []):
                if code and code not in countries:
                    countries.append(code)
        country_set = set(countries)
        has_us = US_CODE in country_set
        has_cn = CN_CODE in country_set
        if has_us and has_cn:
            primary = "Mixed"
        elif has_us:
            primary = "US"
        elif has_cn:
            primary = "China"
        elif country_set:
            primary = "Other"
        else:
            primary = "Unknown"

        papers.append({
            "id":              p.get("id", ""),
            "title":           (p.get("title") or ""),
            "authors":         authors[:3],
            "countries":       countries,
            "primary_country": primary,
            "published":       p.get("publication_date", ""),
            "cited_by_count":  p.get("cited_by_count", 0),
            "source":          "openalex",
        })
    return papers


# ── Composite builder ─────────────────────────────────────────────────────────

def build_talent_composite(
    vol_us: int, vol_cn: int,
    hi_us: int, hi_cn: int,
    tc_us: int, tc_cn: int,
    manual: dict,
) -> dict:
    """
    Build the talent pipeline composite from 3 proxies.
    All share scores are US% of (US + China) combined.
    """

    # ── Proxy 1: Research output quality ──────────────────────────────────────
    def share(a: int, b: int) -> float:
        total = a + b
        return round(a / total * 100, 1) if total > 0 else 50.0

    vol_us_share = share(vol_us, vol_cn)
    vol_cn_share = round(100.0 - vol_us_share, 1)

    hi_ok = hi_us > 0 or hi_cn > 0
    if hi_ok:
        hi_us_share  = share(hi_us, hi_cn)
        hi_cn_share  = round(100.0 - hi_us_share, 1)
    else:
        log.warning("High-impact query returned no data — using seeded estimates")
        hi_us_share, hi_cn_share = 54.0, 46.0

    tc_ok = tc_us > 0 or tc_cn > 0
    if tc_ok:
        tc_us_share  = share(tc_us, tc_cn)
        tc_cn_share  = round(100.0 - tc_us_share, 1)
    else:
        log.warning("Top-cited query returned no data — using seeded estimates")
        tc_us_share, tc_cn_share = 52.0, 48.0

    ro_us_share = round(
        SUB_WEIGHT_VOLUME      * vol_us_share +
        SUB_WEIGHT_HIGH_IMPACT * hi_us_share  +
        SUB_WEIGHT_TOP_CITED   * tc_us_share,
        1,
    )
    ro_cn_share = round(100.0 - ro_us_share, 1)
    log.info("Research output: vol US=%.1f%% | hi-impact US=%.1f%% | top-cited US=%.1f%% | composite US=%.1f%%",
             vol_us_share, hi_us_share, tc_us_share, ro_us_share)

    # ── Proxy 2: Domestic pipeline ────────────────────────────────────────────
    pipeline = manual.get("pipeline", {})
    pl_totals = pipeline.get("adjusted_totals", {})
    pl_us_share = pl_totals.get("us_share_pct", 19.0)
    pl_cn_share = pl_totals.get("china_share_pct", 81.0)
    pl_us_phd   = pipeline.get("us", {}).get("ai_related_phds_estimated", 3667)
    pl_cn_phd   = pipeline.get("china", {}).get("ai_related_phds_estimated", 15600)
    log.info("Pipeline: US PhDs/yr=%d (%.1f%%), China PhDs/yr=%d (%.1f%%)",
             pl_us_phd, pl_us_share, pl_cn_phd, pl_cn_share)

    # ── Proxy 3: Elite concentration + migration ──────────────────────────────
    elite = manual.get("elite_researchers", {})
    em_totals = elite.get("us_china_share", {})
    em_us_share = em_totals.get("us_pct", 72.2)
    em_cn_share = em_totals.get("china_pct", 27.8)
    em_us_count = em_totals.get("us_count_estimate", 1140)
    em_cn_count = em_totals.get("china_count_estimate", 438)
    migration   = elite.get("migration_flows", {})
    log.info("Elite migration: US=%.1f%% China=%.1f%%", em_us_share, em_cn_share)

    # ── Overall composite ─────────────────────────────────────────────────────
    comp_us = round(
        WEIGHT_RESEARCH_OUTPUT * ro_us_share +
        WEIGHT_PIPELINE        * pl_us_share +
        WEIGHT_ELITE_MIGRATION * em_us_share,
        1,
    )
    comp_cn = round(100.0 - comp_us, 1)
    log.info("Talent composite: US=%.1f%% China=%.1f%%", comp_us, comp_cn)

    return {
        "US": {
            "composite_score": comp_us,
            "proxies": {
                "research_output": {
                    "weight":           WEIGHT_RESEARCH_OUTPUT,
                    "share_score":      ro_us_share,
                    "paper_volume": {
                        "raw_value":    vol_us,
                        "share_score":  vol_us_share,
                        "window":       "12m",
                    },
                    "high_impact": {
                        "raw_value":    hi_us,
                        "share_score":  hi_us_share,
                        "window":       "3y",
                        "filter":       "cited_by_count ≥ 50",
                        "data_ok":      hi_ok,
                    },
                    "top_cited": {
                        "raw_value":    tc_us,
                        "share_score":  tc_us_share,
                        "window":       "2y",
                        "filter":       "cited_by_count ≥ 25",
                        "data_ok":      tc_ok,
                    },
                    "sub_weights": {
                        "volume":      SUB_WEIGHT_VOLUME,
                        "high_impact": SUB_WEIGHT_HIGH_IMPACT,
                        "top_cited":   SUB_WEIGHT_TOP_CITED,
                    },
                },
                "pipeline": {
                    "weight":           WEIGHT_PIPELINE,
                    "share_score":      pl_us_share,
                    "phd_annual":       pl_us_phd,
                    "source":           pipeline.get("us", {}).get("source_name", "NSF SDR 2022"),
                    "confidence":       pipeline.get("us", {}).get("confidence", "High"),
                },
                "elite_migration": {
                    "weight":           WEIGHT_ELITE_MIGRATION,
                    "share_score":      em_us_share,
                    "researcher_count_est": em_us_count,
                    "source":           elite.get("source", {}).get("name", "MacroPolo AI Talent Tracker 2023"),
                    "confidence":       elite.get("source", {}).get("confidence", "Medium-High"),
                    "migration_note":   migration.get("trend", ""),
                },
            },
        },
        "China": {
            "composite_score": comp_cn,
            "proxies": {
                "research_output": {
                    "weight":           WEIGHT_RESEARCH_OUTPUT,
                    "share_score":      ro_cn_share,
                    "paper_volume": {
                        "raw_value":    vol_cn,
                        "share_score":  vol_cn_share,
                        "window":       "12m",
                    },
                    "high_impact": {
                        "raw_value":    hi_cn,
                        "share_score":  hi_cn_share,
                        "window":       "3y",
                        "filter":       "cited_by_count ≥ 50",
                        "data_ok":      hi_ok,
                    },
                    "top_cited": {
                        "raw_value":    tc_cn,
                        "share_score":  tc_cn_share,
                        "window":       "2y",
                        "filter":       "cited_by_count ≥ 25",
                        "data_ok":      tc_ok,
                    },
                    "sub_weights": {
                        "volume":      SUB_WEIGHT_VOLUME,
                        "high_impact": SUB_WEIGHT_HIGH_IMPACT,
                        "top_cited":   SUB_WEIGHT_TOP_CITED,
                    },
                },
                "pipeline": {
                    "weight":           WEIGHT_PIPELINE,
                    "share_score":      pl_cn_share,
                    "phd_annual":       pl_cn_phd,
                    "source":           pipeline.get("china", {}).get("source_name", "China MoE 2022"),
                    "confidence":       pipeline.get("china", {}).get("confidence", "Medium"),
                    "coverage_note":    pipeline.get("china", {}).get("methodology_note", ""),
                },
                "elite_migration": {
                    "weight":           WEIGHT_ELITE_MIGRATION,
                    "share_score":      em_cn_share,
                    "researcher_count_est": em_cn_count,
                    "source":           elite.get("source", {}).get("name", "MacroPolo AI Talent Tracker 2023"),
                    "confidence":       elite.get("source", {}).get("confidence", "Medium-High"),
                    "migration_note":   migration.get("trend", ""),
                },
            },
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    manual = load_manual_data()

    today      = datetime.now(timezone.utc).date()
    cutoff_12m = (today - timedelta(days=365)).isoformat()
    cutoff_2y  = (today - timedelta(days=730)).isoformat()
    cutoff_3y  = (today - timedelta(days=1095)).isoformat()
    today_str  = today.isoformat()

    base_filter = f"concepts.id:{CONCEPTS},to_publication_date:{today_str}"

    # ── Call 1: Paper volume (12m) ────────────────────────────────────────────
    log.info("Fetching paper volume (12m) …")
    vol_filter = f"{base_filter},from_publication_date:{cutoff_12m}"
    vol_breakdown, vol_total = fetch_country_breakdown(vol_filter, "volume")
    time.sleep(RATE_LIMIT_SLEEP)
    vol_us, vol_cn = extract_us_cn(vol_breakdown)

    # ── Call 2: High-impact papers (3y, cited ≥ 50) ───────────────────────────
    log.info("Fetching high-impact papers (3y, cited ≥ 50) …")
    hi_filter = f"{base_filter},from_publication_date:{cutoff_3y},cited_by_count:>50"
    hi_breakdown, hi_total = fetch_country_breakdown(hi_filter, "high-impact")
    time.sleep(RATE_LIMIT_SLEEP)
    hi_us, hi_cn = extract_us_cn(hi_breakdown)

    # ── Call 3: Top-cited papers (2y, cited ≥ 25) ─────────────────────────────
    log.info("Fetching top-cited papers (2y, cited ≥ 25) …")
    tc_filter = f"{base_filter},from_publication_date:{cutoff_2y},cited_by_count:>25"
    tc_breakdown, tc_total = fetch_country_breakdown(tc_filter, "top-cited")
    time.sleep(RATE_LIMIT_SLEEP)
    tc_us, tc_cn = extract_us_cn(tc_breakdown)

    if vol_us == 0 and vol_cn == 0:
        log.error("Paper volume query returned 0 for both US and China — aborting")
        sys.exit(1)

    # ── Call 4: Recent papers table ───────────────────────────────────────────
    log.info("Fetching recent papers for table …")
    recent_papers = fetch_recent_papers(vol_filter, MAX_PAPERS_TABLE)
    log.info("  → %d papers retrieved", len(recent_papers))

    # ── Top countries for context ─────────────────────────────────────────────
    top_countries = sorted(
        [{"country_code": k, "count": v} for k, v in vol_breakdown.items() if k],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    # ── Build composite ───────────────────────────────────────────────────────
    composite = build_talent_composite(
        vol_us, vol_cn,
        hi_us, hi_cn,
        tc_us, tc_cn,
        manual,
    )

    output = {
        "schema_version": "2.0",
        "dimension":      "talent",
        "metric_key":     "talent_pipeline_index",
        "description": (
            "Talent pipeline index: research output quality (35%, OpenAlex), "
            "domestic PhD pipeline (25%, NSF/MoE), and elite researcher "
            "concentration + migration (40%, MacroPolo). "
            "See talent_manual.json for pipeline and migration data sources."
        ),
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "weights": {
            "research_output": WEIGHT_RESEARCH_OUTPUT,
            "pipeline":        WEIGHT_PIPELINE,
            "elite_migration": WEIGHT_ELITE_MIGRATION,
        },
        "summary": {
            "US":    composite["US"],
            "China": composite["China"],
        },
        "openalex": {
            "source_url":     OPENALEX_BASE,
            "concepts":       CONCEPTS,
            "window_days_volume":      365,
            "window_days_high_impact": 1095,
            "window_days_top_cited":   730,
            "high_impact_min_cites":   50,
            "top_cited_min_cites":     25,
            "methodology_note": (
                "Papers counted once per country where ≥1 author has an identified "
                "institution. Multinational papers counted in both countries — sums "
                "exceed total paper count. High-impact and top-cited queries add a "
                "cited_by_count filter which may not work on all OpenAlex instances "
                "(falls back to seeded estimates if the filter returns zero results). "
                "OpenAlex does not de-duplicate authors across papers; a prolific "
                "researcher counts once per paper, not once per researcher."
            ),
            "top_countries":  top_countries,
            "volume": {
                "us": vol_us, "china": vol_cn, "total": vol_total,
                "data_ok": vol_us > 0 or vol_cn > 0,
            },
            "high_impact": {
                "us": hi_us, "china": hi_cn, "total": hi_total,
                "data_ok": hi_us > 0 or hi_cn > 0,
            },
            "top_cited": {
                "us": tc_us, "china": tc_cn, "total": tc_total,
                "data_ok": tc_us > 0 or tc_cn > 0,
            },
        },
        "manual_data_snapshot": manual.get("last_updated", "unknown"),
        "coverage_warning": manual.get("coverage_warning", ""),
        "papers": recent_papers,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("Talent composite: US=%.1f China=%.1f (each out of 100)",
             composite["US"]["composite_score"],
             composite["China"]["composite_score"])


if __name__ == "__main__":
    main()
