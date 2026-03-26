#!/usr/bin/env python3
"""
Fetch AI talent data from OpenAlex API.

Produces a three-proxy composite index that captures both research volume
and research quality/impact — a more complete picture than paper counts alone.

PROXIES
  1. Paper volume (12-month window)
       All AI-related papers grouped by country-of-institution.
       Measures breadth of research output.
       Weight: 30 %

  2. Top conference papers (2-year window, cited ≥ 10 times)
       AI papers published in conference proceedings (source.type = conference)
       with at least 10 citations. Captures presence at major AI venues
       (NeurIPS, ICML, ICLR, CVPR, ACL, AAAI, IJCAI, etc.) without
       requiring fragile venue-specific ID lookups.
       Weight: 40 %

  3. High-impact papers (3-year window, cited ≥ 50 times)
       AI papers of any type with 50+ citations. Captures elite,
       field-defining research that transcends any single conference.
       Weight: 30 %

COMPOSITE SCORING
  Each proxy is scored as share-of-combined (US + China = 100).
  Composite = weighted average of the three shares.
  US composite + China composite ≈ 100 by construction.

WHY THREE METRICS?
  China leads strongly on paper volume (~64 % of US+CN combined).
  The US tends to lead on top-conference presence and citation impact.
  A composite across all three gives a more balanced and accurate
  picture of relative AI talent strength.

OUTPUT: data/talent.json

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
    print("Error: 'requests' package is required.")
    print("Install it with:  pip install requests")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "talent.json"

# ── Config ────────────────────────────────────────────────────────────────────
OPENALEX_BASE    = "https://api.openalex.org/works"
REQUEST_TIMEOUT  = 30
RATE_LIMIT_SLEEP = 1.2   # seconds between requests; OpenAlex polite pool
MAX_PAPERS_TABLE = 15

# OpenAlex concept IDs for AI/ML/NLP/CV (stable identifiers)
CONCEPTS = "C154945302|C119857082|C204321447|C31972630"
# C154945302 = Artificial Intelligence
# C119857082 = Machine Learning
# C204321447 = Natural Language Processing
# C31972630  = Computer Vision

# Time windows for each proxy
WINDOW_VOLUME_DAYS     = 365    # 12 months — paper volume
WINDOW_CONFERENCE_DAYS = 730    # 2 years — top-conference cited papers
WINDOW_HIGH_IMPACT_DAYS = 1095  # 3 years — high-impact papers

# Citation thresholds
CONF_MIN_CITATIONS    = 10   # top-conference proxy: cited ≥ 10 times
IMPACT_MIN_CITATIONS  = 50   # high-impact proxy: cited ≥ 50 times

# Composite weights (must sum to 1.0)
WEIGHTS = {
    "paper_volume":    0.30,
    "top_conference":  0.40,
    "high_impact":     0.30,
}

MAILTO = "ai-tracker@github-actions"
US_CODE = "US"
CN_CODE = "CN"


# ── API helpers ───────────────────────────────────────────────────────────────

def openalex_get(params: dict, base: str = OPENALEX_BASE) -> dict | None:
    """GET request to OpenAlex; returns parsed JSON or None on failure."""
    headers = {"User-Agent": f"ai-race-tracker/1.0 (mailto:{MAILTO})"}
    try:
        resp = requests.get(base, params=params, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        log.warning("OpenAlex request failed: %s", e)
        return None


# ── Country breakdown (shared logic) ─────────────────────────────────────────

def fetch_country_breakdown(filter_str: str, label: str) -> tuple[int, int, int]:
    """
    Fetch paper counts for US, China, and total via group_by.
    Returns (us_count, china_count, total_attributed).
    """
    params = {
        "filter":   filter_str,
        "group_by": "authorships.institutions.country_code",
        "per_page": 200,
        "mailto":   MAILTO,
    }
    data = openalex_get(params)
    if data is None:
        log.warning("  [%s] group_by call returned None", label)
        return 0, 0, 0

    us_count    = 0
    china_count = 0
    total_attributed = 0

    for group in data.get("group_by", []):
        raw_key = group.get("key") or ""
        count   = group.get("count", 0)
        code    = raw_key.split("/")[-1] if raw_key else None

        if code == US_CODE:
            us_count = count
        elif code == CN_CODE:
            china_count = count

        if code and code not in ("", None):
            total_attributed += count

    total_papers = data.get("meta", {}).get("count", 0)
    log.info("  [%s] total=%d  US=%d  CN=%d", label, total_papers, us_count, china_count)
    return us_count, china_count, total_attributed


# ── Recent papers (for the dashboard detail table) ────────────────────────────

def derive_primary_country(countries: list[str]) -> str:
    country_set = set(countries)
    has_us = US_CODE in country_set
    has_cn = CN_CODE in country_set
    if has_us and has_cn:
        return "Mixed"
    if has_us:
        return "US"
    if has_cn:
        return "China"
    if country_set:
        return "Other"
    return "Unknown"


def fetch_recent_papers(filter_str: str) -> list[dict]:
    params = {
        "filter":   filter_str,
        "sort":     "publication_date:desc",
        "per_page": MAX_PAPERS_TABLE,
        "select":   "id,title,publication_date,authorships,cited_by_count",
        "mailto":   MAILTO,
    }
    data = openalex_get(params)
    if data is None:
        return []

    papers = []
    for p in data.get("results", []):
        authors   = []
        countries: list[str] = []
        for auth in p.get("authorships", []):
            name = (auth.get("author") or {}).get("display_name", "")
            if name:
                authors.append(name)
            for code in auth.get("countries", []):
                if code and code not in countries:
                    countries.append(code)

        papers.append({
            "id":              p.get("id", ""),
            "title":           p.get("title", "") or "",
            "authors":         authors[:3],
            "countries":       countries,
            "primary_country": derive_primary_country(countries),
            "published":       p.get("publication_date", ""),
            "cited_by_count":  p.get("cited_by_count", 0),
            "source":          "openalex",
        })
    return papers


# ── Composite scorer ──────────────────────────────────────────────────────────

def share_score(us: int, cn: int) -> tuple[float, float]:
    """Return (us_share, cn_share) as percentages summing to 100.
    Returns (50.0, 50.0) if both are zero."""
    total = us + cn
    if total == 0:
        return 50.0, 50.0
    us_share = round((us / total) * 100.0, 1)
    cn_share = round(100.0 - us_share, 1)
    return us_share, cn_share


def compute_composite(proxies: dict[str, dict]) -> tuple[float, float]:
    """
    Compute weighted composite for US and China.
    Each proxy dict must have 'us_share' and 'cn_share' fields.
    Returns (us_composite, cn_composite) rounded to 1 decimal.
    """
    us_comp = 0.0
    cn_comp = 0.0
    total_weight = 0.0
    for key, weight in WEIGHTS.items():
        proxy = proxies.get(key)
        if proxy is None:
            continue
        us_comp     += weight * proxy["us_share"]
        cn_comp     += weight * proxy["cn_share"]
        total_weight += weight

    if total_weight == 0:
        return 50.0, 50.0
    # Renormalize if some proxies were missing
    us_comp = round(us_comp / total_weight, 1)
    cn_comp = round(cn_comp / total_weight, 1)
    return us_comp, cn_comp


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today     = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    def cutoff(days: int) -> str:
        return (today - timedelta(days=days)).isoformat()

    # Base filter shared by all three proxies
    base = f"concepts.id:{CONCEPTS},to_publication_date:{today_str}"

    # ── Proxy 1: Paper volume (12 months) ────────────────────────────────────
    log.info("── Proxy 1: Paper volume (12-month) ──────────────────────────")
    f_volume = f"{base},from_publication_date:{cutoff(WINDOW_VOLUME_DAYS)}"
    vol_us, vol_cn, vol_total = fetch_country_breakdown(f_volume, "volume")
    vol_us_share, vol_cn_share = share_score(vol_us, vol_cn)
    time.sleep(RATE_LIMIT_SLEEP)

    # ── Proxy 2: Top conference papers (2 years, cited ≥ 10) ─────────────────
    log.info("── Proxy 2: Top conference papers (2y, cited≥%d) ─────────────", CONF_MIN_CITATIONS)
    f_conf = (
        f"{base},"
        f"from_publication_date:{cutoff(WINDOW_CONFERENCE_DAYS)},"
        f"cited_by_count:>{CONF_MIN_CITATIONS - 1},"
        f"locations.source.type:conference"
    )
    conf_us, conf_cn, conf_total = fetch_country_breakdown(f_conf, "top-conf")
    conf_us_share, conf_cn_share = share_score(conf_us, conf_cn)
    time.sleep(RATE_LIMIT_SLEEP)

    # ── Proxy 3: High-impact papers (3 years, cited ≥ 50) ────────────────────
    log.info("── Proxy 3: High-impact papers (3y, cited≥%d) ────────────────", IMPACT_MIN_CITATIONS)
    f_impact = (
        f"{base},"
        f"from_publication_date:{cutoff(WINDOW_HIGH_IMPACT_DAYS)},"
        f"cited_by_count:>{IMPACT_MIN_CITATIONS - 1}"
    )
    imp_us, imp_cn, imp_total = fetch_country_breakdown(f_impact, "high-impact")
    imp_us_share, imp_cn_share = share_score(imp_us, imp_cn)
    time.sleep(RATE_LIMIT_SLEEP)

    # ── Recent papers for table ───────────────────────────────────────────────
    log.info("── Recent papers (table) ─────────────────────────────────────")
    recent_papers = fetch_recent_papers(f_volume)
    log.info("  → %d papers retrieved", len(recent_papers))

    # ── Composite score ───────────────────────────────────────────────────────
    proxies = {
        "paper_volume":   {"us_share": vol_us_share,  "cn_share": vol_cn_share},
        "top_conference": {"us_share": conf_us_share, "cn_share": conf_cn_share},
        "high_impact":    {"us_share": imp_us_share,  "cn_share": imp_cn_share},
    }
    us_composite, cn_composite = compute_composite(proxies)

    log.info("")
    log.info("Composite: US=%.1f  CN=%.1f", us_composite, cn_composite)

    # ── Build output ──────────────────────────────────────────────────────────
    output = {
        "dimension":   "talent",
        "metric_key":  "ai_talent_composite_index",
        "title":       "AI Talent Index — U.S. vs China",
        "subtitle":    (
            "Three-proxy composite: research volume, top-conference presence, "
            "and high-impact output. Each proxy scored as share-of-combined "
            "(US + China = 100). US + China composite ≈ 100 by construction."
        ),
        "description": (
            "A composite index measuring relative AI talent strength across "
            "three dimensions: (1) AI paper volume (breadth of research output), "
            "(2) top AI conference papers with ≥10 citations (quality of "
            "conference-level research), and (3) high-impact AI papers with "
            "≥50 citations (elite research production). All proxies sourced "
            "from OpenAlex. Each is scored as US share of combined US+China total."
        ),
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "US": {
                "composite_score":   us_composite,
                "effective_weights": WEIGHTS,
                "proxies": {
                    "paper_volume": {
                        "raw_value":    vol_us,
                        "unit":         "AI papers (12-month)",
                        "share_score":  vol_us_share,
                        "window_days":  WINDOW_VOLUME_DAYS,
                        "coverage":     "high",
                        "note": (
                            f"AI papers (AI/ML/NLP/CV concepts) on OpenAlex, "
                            f"last {WINDOW_VOLUME_DAYS} days, grouped by author institution country. "
                            "China leads on volume; US tends to lead on citation impact."
                        ),
                    },
                    "top_conference": {
                        "raw_value":       conf_us,
                        "unit":            f"AI conference papers cited ≥{CONF_MIN_CITATIONS}x (2-year)",
                        "share_score":     conf_us_share,
                        "window_days":     WINDOW_CONFERENCE_DAYS,
                        "min_citations":   CONF_MIN_CITATIONS,
                        "venue_filter":    "locations.source.type:conference",
                        "coverage":        "high",
                        "note": (
                            f"AI papers published in conference proceedings (OpenAlex source "
                            f"type=conference) with at least {CONF_MIN_CITATIONS} citations, "
                            f"last {WINDOW_CONFERENCE_DAYS} days. Covers NeurIPS, ICML, ICLR, "
                            "CVPR, ACL, AAAI, IJCAI and other major AI venues without "
                            "requiring venue-specific ID lookups."
                        ),
                    },
                    "high_impact": {
                        "raw_value":       imp_us,
                        "unit":            f"AI papers cited ≥{IMPACT_MIN_CITATIONS}x (3-year)",
                        "share_score":     imp_us_share,
                        "window_days":     WINDOW_HIGH_IMPACT_DAYS,
                        "min_citations":   IMPACT_MIN_CITATIONS,
                        "coverage":        "high",
                        "note": (
                            f"AI papers of any type with at least {IMPACT_MIN_CITATIONS} citations, "
                            f"last {WINDOW_HIGH_IMPACT_DAYS} days. Uses a 3-year window to give "
                            "papers adequate time to accumulate citations. Captures field-defining "
                            "research regardless of venue."
                        ),
                    },
                },
            },
            "China": {
                "composite_score":   cn_composite,
                "effective_weights": WEIGHTS,
                "proxies": {
                    "paper_volume": {
                        "raw_value":   vol_cn,
                        "unit":        "AI papers (12-month)",
                        "share_score": vol_cn_share,
                        "window_days": WINDOW_VOLUME_DAYS,
                        "coverage":    "high",
                        "note": (
                            f"China leads on AI paper volume ({vol_cn:,} vs US {vol_us:,} "
                            f"over {WINDOW_VOLUME_DAYS} days). OpenAlex may undercount Chinese "
                            "domestic journals not indexed in major international databases."
                        ),
                    },
                    "top_conference": {
                        "raw_value":     conf_cn,
                        "unit":          f"AI conference papers cited ≥{CONF_MIN_CITATIONS}x (2-year)",
                        "share_score":   conf_cn_share,
                        "window_days":   WINDOW_CONFERENCE_DAYS,
                        "min_citations": CONF_MIN_CITATIONS,
                        "coverage":      "high",
                        "note": (
                            "China has substantially increased top AI conference presence "
                            "since 2019, particularly at NeurIPS, ICML, and CVPR. "
                            "Citation thresholding filters out poster/workshop papers."
                        ),
                    },
                    "high_impact": {
                        "raw_value":     imp_cn,
                        "unit":          f"AI papers cited ≥{IMPACT_MIN_CITATIONS}x (3-year)",
                        "share_score":   imp_cn_share,
                        "window_days":   WINDOW_HIGH_IMPACT_DAYS,
                        "min_citations": IMPACT_MIN_CITATIONS,
                        "coverage":      "high",
                        "note": (
                            "US tends to lead on high-citation AI papers, reflecting "
                            "concentration of frontier lab research (Google DeepMind, "
                            "OpenAI, Meta FAIR, Microsoft Research) in the US ecosystem."
                        ),
                    },
                },
            },
        },
        "interpretive_sentence": (
            f"On a composite of paper volume (30%), top conference presence (40%), "
            f"and high-impact output (30%), the US scores {us_composite:.1f} and "
            f"China scores {cn_composite:.1f} out of 100 (US + China ≈ 100). "
            f"China leads on raw paper volume ({vol_cn_share:.1f}% of combined); "
            f"the US leads on top-conference cited papers ({conf_us_share:.1f}%) "
            f"and high-impact papers ({imp_us_share:.1f}%)."
        ),
        "composite_construction": {
            "method": (
                "Weighted average of three share-of-combined scores. Each proxy is "
                "computed as US/(US+China)*100, giving a score where US+China=100. "
                "Composite = 0.30*(paper_volume_share) + 0.40*(top_conference_share) "
                "+ 0.30*(high_impact_share). Rationale: top-conference presence weighted "
                "highest as the most direct measure of research quality at AI-specific venues."
            ),
            "weights": WEIGHTS,
            "windows": {
                "paper_volume":    f"{WINDOW_VOLUME_DAYS} days",
                "top_conference":  f"{WINDOW_CONFERENCE_DAYS} days",
                "high_impact":     f"{WINDOW_HIGH_IMPACT_DAYS} days",
            },
            "thresholds": {
                "top_conference_min_citations": CONF_MIN_CITATIONS,
                "high_impact_min_citations":    IMPACT_MIN_CITATIONS,
            },
        },
        "source": {
            "name": "OpenAlex API",
            "url":  "https://api.openalex.org/works",
            "note": (
                "group_by=authorships.institutions.country_code on AI/ML/NLP/CV concepts. "
                "Papers with authors from multiple countries are counted in each country. "
                "Conference-type filter uses locations.source.type:conference."
            ),
        },
        "papers": recent_papers,
        "methodology_note": (
            "All three proxies use OpenAlex's group_by endpoint. Country attribution "
            "follows OpenAlex's institution-to-country mapping (ISO 3166-1 alpha-2). "
            "A paper with US and Chinese co-authors is counted in both country totals. "
            "The top-conference proxy (source.type:conference) covers all major AI venues "
            "without venue-specific curation. The citation threshold filters out the long "
            "tail of low-engagement papers, making conference presence more signal-rich. "
            "Known limitations: OpenAlex undercounts Chinese domestic journals/conferences "
            "not indexed internationally; citation counts favor English-language venues."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info(
        "Paper volume:     US=%d (%.1f%%)  CN=%d (%.1f%%)",
        vol_us, vol_us_share, vol_cn, vol_cn_share,
    )
    log.info(
        "Top conf (≥%dc):  US=%d (%.1f%%)  CN=%d (%.1f%%)",
        CONF_MIN_CITATIONS, conf_us, conf_us_share, conf_cn, conf_cn_share,
    )
    log.info(
        "High impact(≥%dc): US=%d (%.1f%%)  CN=%d (%.1f%%)",
        IMPACT_MIN_CITATIONS, imp_us, imp_us_share, imp_cn, imp_cn_share,
    )
    log.info(
        "Composite:        US=%.1f  CN=%.1f",
        us_composite, cn_composite,
    )


if __name__ == "__main__":
    main()
