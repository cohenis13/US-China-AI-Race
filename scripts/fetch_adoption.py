#!/usr/bin/env python3
"""
AI Adoption Index — composite proxy for economy-wide AI adoption.

APPROACH
  Builds a two-proxy composite index comparing US vs China on AI adoption,
  using the best available publicly comparable data.

  Proxy 1 — Gen-AI Enterprise Adoption Rate (60% weight):
    The share of business decision-makers at firms using generative AI.
    Source: SAS Institute / Coleman Parkes Research, 2024 global survey
    (Reuters, July 2024). 1,600 respondents across 17 countries.
    WHY THIS SOURCE: The only publicly available survey that asked the same
    question with the same methodology in both the US and China directly.
    McKinsey, OECD, and Stanford AI Index all lack comparable China-specific
    breakdowns, or conflate Asia-Pacific/MENA regional data with China figures.
    Confidence: medium — proprietary survey, sampling details not fully public.
    US: 65%, China: 83% (China leads on gen-AI adoption at the firm level).

  Proxy 2 — Industrial Robot Density (40% weight):
    Installed industrial robots per 10,000 manufacturing workers.
    Source: IFR (International Federation of Robotics) World Robotics 2024
    (October 2024, covering 2023 operational data).
    WHY THIS SOURCE: Highest-symmetry available metric — same methodology,
    same reporting body, directly country-comparable. Captures industrial
    AI/automation deployment at scale; understates software-only AI.
    US: 295, China: 470 (China overtook Japan and Germany in 2023).

SUPPLEMENTARY (not in composite):
  OECD ICT Business Survey: US enterprise AI use (% of firms, all sizes).
    Fetched live from OECD API where available; hardcoded fallback used
    when the API is unavailable (common on local runs due to OECD rate limits).
    Not usable for China — OECD does not cover China in ICT surveys.

  CAICT Manufacturing AI Adoption: China manufacturing AI application share.
    Hardcoded from CAICT AI White Paper 2025 (March 2025): 25.9% of smart
    manufacturing enterprises using AI, up from 19.9% in 2024.
    Shown as China context only; not used in composite (no comparable US metric
    using the same definition).

WHY TWO PROXIES AND NOT THREE
  Adding a third proxy from OECD (US-only coverage) would create an asymmetric
  composite where the US has three inputs and China has two, distorting scores
  in a non-transparent way. Supplementary data is shown separately instead.

COMPOSITE CONSTRUCTION
  Normalization:
    - Gen-AI adoption: already expressed as %; used directly (0–100).
    - Robot density: (value / ROBOT_DENSITY_NORM_MAX) × 100
      where ROBOT_DENSITY_NORM_MAX = 600 robots/10K workers.

  Composite = 0.60 × gen_ai_norm + 0.40 × robot_density_norm

TO UPDATE REFERENCE DATA
  SAS survey: Update GEN_AI_ADOPTION values when a new edition is published.
  IFR: Update ROBOT_DENSITY values when IFR publishes their annual report
    (~October each year, covering the prior year's data).
  OECD: OECD_FALLBACK_US is updated when OECD publishes new ICT data
    (~January each year for the prior year).

  Next expected updates:
    - IFR World Robotics 2025: ~October 2025 (will cover 2024 data)
    - SAS / Coleman Parkes next survey: unclear (was one-time as of 2024)
    - OECD ICT 2026: ~January 2026 (for 2025 data)

Outputs to data/adoption.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "adoption.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_GEN_AI = 0.60   # gen-AI adoption rate (SAS/Coleman Parkes, direct US-China comparison)
WEIGHT_ROBOT  = 0.40   # industrial robot density (IFR, symmetric country data)

# ── Robot density normalization reference ─────────────────────────────────────
# 600 robots/10K workers: above leading OECD economies (~430), gives headroom
# for China (470) while keeping both countries in a meaningful score range.
# South Korea (~1,012) is excluded as a global outlier and not used as ceiling.
ROBOT_DENSITY_NORM_MAX = 600.0

# ── Proxy 1: Gen-AI Enterprise Adoption Rate ─────────────────────────────────
# Source: SAS Institute / Coleman Parkes Research (Reuters, July 2024)
# Survey: 1,600 business decision-makers across 17 countries
# Question: Share of firms where decision-makers report using generative AI
# URL: https://www.reuters.com/technology/artificial-intelligence/
#       china-leads-world-adoption-generative-ai-survey-shows-2024-07-09/
#
# Notes:
#   US: 65% of business decision-makers using gen AI (2024, SAS survey)
#   China: 83% of business decision-makers using gen AI (2024, SAS survey)
#   Global average: 54% in same survey.
#
#   China's higher rate is consistent with CAICT reports and Stanford AI Index
#   2025, which show aggressive enterprise AI rollout in manufacturing and tech.
#   The 18-point gap is directionally robust across multiple sources.
#
#   Alternative reference points (shown as supplementary data):
#     - McKinsey 2025 (North America): ~72% organizations using AI (any function)
#     - OECD 2025 average: ~20.2% of firms using AI (narrower definition)
#     - Stanford AI Index 2025: ~78% of organizations using AI globally
#   These use different definitions and populations — not used in composite.
#
# TO UPDATE: Change value, source_url, and survey_year when a new directly
#            comparable US-China survey is published.
GEN_AI_ADOPTION = {
    "US": {
        "value":       65.0,   # percent of business decision-makers using gen AI
        "coverage":    "medium",
        "survey_year": 2024,
        "note": (
            "SAS Institute / Coleman Parkes Research 2024 (Reuters, July 2024). "
            "1,600 business decision-makers across 17 countries. US: 65% using "
            "gen AI vs global average 54% and China 83%. "
            "Source: https://www.reuters.com/technology/artificial-intelligence/"
            "china-leads-world-adoption-generative-ai-survey-shows-2024-07-09/"
        ),
    },
    "China": {
        "value":       83.0,   # percent of business decision-makers using gen AI
        "coverage":    "medium",
        "survey_year": 2024,
        "note": (
            "SAS Institute / Coleman Parkes Research 2024 (Reuters, July 2024). "
            "China: 83% of business decision-makers using gen AI — highest of all "
            "17 countries surveyed. Consistent with CAICT AI White Paper 2025 and "
            "Stanford AI Index 2025 showing rapid enterprise AI rollout in China. "
            "Source: https://www.reuters.com/technology/artificial-intelligence/"
            "china-leads-world-adoption-generative-ai-survey-shows-2024-07-09/"
        ),
    },
}

GEN_AI_META = {
    "source_name":    "SAS Institute / Coleman Parkes Research, Global Gen-AI Survey",
    "source_url":     "https://www.reuters.com/technology/artificial-intelligence/china-leads-world-adoption-generative-ai-survey-shows-2024-07-09/",
    "edition":        "2024 (published July 2024)",
    "definition":     "% of business decision-makers at firms using generative AI",
    "sample":         "1,600 respondents across 17 countries",
    "update_cadence": "Uncertain — single known edition as of 2024; monitor for annual follow-up",
    "why_primary": (
        "The only publicly available survey that measured gen-AI adoption with the "
        "same instrument for both the US and China. McKinsey and OECD do not provide "
        "directly comparable China-specific breakdowns."
    ),
}

# ── Proxy 2: Industrial Robot Density ────────────────────────────────────────
# Source: IFR World Robotics 2024 (October 2024, 2023 operational data)
# Definition: Installed industrial robots per 10,000 manufacturing workers
#
# 2023 values:
#   China: 470 robots/10K workers (up from 392 in 2022 — overtook Japan/Germany)
#   US:    295 robots/10K workers (up from 274 in 2022)
#   Reference: South Korea 1,012 (global outlier); Germany 429; Japan 419
#
# TO UPDATE: Change value and edition when IFR publishes its annual report
#            (expected ~October each year, covering prior-year data).
ROBOT_DENSITY = {
    "US": {
        "value":    295,
        "coverage": "high",
        "note":     "IFR World Robotics 2024 (2023 data), United States",
    },
    "China": {
        "value":    470,
        "coverage": "high",
        "note": (
            "IFR World Robotics 2024 (2023 data), China — overtook Japan and "
            "Germany in robot density ranking; up from 392 in 2022"
        ),
    },
}

ROBOT_DENSITY_META = {
    "source_name":    "International Federation of Robotics (IFR), World Robotics 2024",
    "source_url":     "https://ifr.org/ifr-press-releases/news/robot-density-nearly-doubled-globally",
    "edition":        "2024 report (October 2024, 2023 operational data)",
    "definition":     "Installed industrial robots per 10,000 manufacturing workers",
    "update_cadence": "Annual (typically October, covering prior year's data)",
}

# ── Supplementary: OECD ICT Business Survey (US only) ────────────────────────
# OECD publishes % of enterprises (≥10 employees) using AI, by country.
# Coverage: OECD member states only — China is NOT included.
# Latest OECD headline: 20.2% of firms in OECD economies use AI (2025 data,
# published January 2026). US-specific figure typically above OECD average.
#
# Fetched live below; this is the hardcoded fallback used when the API fails.
OECD_FALLBACK_US = {
    "value":      20.2,   # OECD average (Jan 2026); US-specific may differ
    "is_average": True,   # True = OECD economy average, not US-specific
    "year":       2025,
    "source":     "OECD ICT Access and Usage Database, Jan 2026 release",
    "source_url": "https://www.oecd.org/en/about/news/announcements/2026/01/ai-use-by-individuals-surges-across-the-oecd-as-adoption-by-firms-continues-to-expand.html",
    "note":       "OECD does not cover China; US-specific figure requires API query.",
}

# OECD API candidates (tried in order; first success wins)
# Dataset: ICT_BUS — ICT Access and Usage by Businesses
# Indicator codes for enterprise AI use vary by OECD release version
OECD_API_URLS = [
    # New OECD SDMX REST API (2024+)
    "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_ICT_BUS@DF_ICT_BUS,1.0/USA..E_AI....?format=csvfilewithlabels&startPeriod=2022",
    # Legacy OECD.Stat SDMX-JSON API
    "https://stats.oecd.org/SDMX-JSON/data/ICT_BUS/USA.E_AI.../all?contentType=csv&startTime=2022",
]
OECD_TIMEOUT = 10   # seconds

# ── CAICT supplementary (China manufacturing AI, context only) ────────────────
# Source: CAICT AI White Paper 2025 (March 2025, published in English)
# URL: https://www.caict.ac.cn/english/research/whitepapers/202503/t20250319_658668.html
# Metric: Share of smart manufacturing enterprises deploying AI applications
# 2025: 25.9% (up from 19.9% in 2024)
# NOTE: Not comparable to the SAS gen-AI survey (different sample, definition,
#       and methodology). Shown as context to illustrate China's industrial AI
#       deployment trajectory; excluded from composite.
CAICT_CHINA_MFG = {
    "value":        25.9,
    "prior_value":  19.9,
    "year":         2025,
    "prior_year":   2024,
    "definition":   "% of smart manufacturing enterprises deploying AI applications",
    "source":       "CAICT AI White Paper 2025 (March 2025)",
    "source_url":   "https://www.caict.ac.cn/english/research/whitepapers/202503/t20250319_658668.html",
    "note": (
        "CAICT (China Academy of Information and Communications Technology) "
        "white paper — government-linked source; methodology not fully public. "
        "Shown as context for China's industrial AI trajectory only."
    ),
}


# ── Live OECD fetch ───────────────────────────────────────────────────────────
def fetch_oecd_us_ai_adoption() -> dict | None:
    """
    Attempt to fetch the US enterprise AI adoption rate from OECD ICT API.
    Returns a dict with value, year, source on success; None on failure.
    Tries multiple API URL patterns; OECD APIs are not always stable.
    """
    headers = {
        "User-Agent": "us-china-ai-tracker research@github-actions.io",
        "Accept":     "text/csv, application/json, */*",
    }
    for url in OECD_API_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=OECD_TIMEOUT)
            if r.status_code == 200 and len(r.text) > 100:
                # Parse CSV — look for USA rows with a numeric AI-use value
                lines = r.text.strip().splitlines()
                if not lines:
                    continue
                header = [h.strip().strip('"').upper() for h in lines[0].split(",")]
                val_col = next(
                    (i for i, h in enumerate(header) if h in ("OBS_VALUE", "VALUE", "OBSVALUE")),
                    None,
                )
                yr_col = next(
                    (i for i, h in enumerate(header) if h in ("TIME_PERIOD", "TIME", "YEAR", "PERIOD")),
                    None,
                )
                if val_col is None:
                    log.info("OECD CSV: could not find value column in %s", header)
                    continue
                # Take most recent row with a valid numeric value
                best_val, best_yr = None, None
                for line in lines[1:]:
                    cols = line.split(",")
                    if len(cols) <= val_col:
                        continue
                    raw = cols[val_col].strip().strip('"')
                    if not raw:
                        continue
                    try:
                        v = float(raw)
                    except ValueError:
                        continue
                    yr = int(cols[yr_col].strip().strip('"')[:4]) if yr_col is not None and len(cols) > yr_col else None
                    if best_yr is None or (yr is not None and yr > best_yr):
                        best_val, best_yr = v, yr
                if best_val is not None:
                    log.info("OECD API: US enterprise AI adoption = %.1f%% (%s)", best_val, best_yr)
                    return {
                        "value":      round(best_val, 1),
                        "year":       best_yr,
                        "is_average": False,
                        "source":     "OECD ICT Access and Usage Database (live)",
                        "source_url": "https://www.oecd.org/en/about/news/announcements/2026/01/ai-use-by-individuals-surges-across-the-oecd-as-adoption-by-firms-continues-to-expand.html",
                        "note":       "Fetched live from OECD SDMX API.",
                    }
            else:
                log.info("OECD API %s → HTTP %s", url[:60], r.status_code)
        except Exception as exc:
            log.info("OECD API %s → %s", url[:60], exc)
    log.info("OECD API unavailable — using hardcoded fallback")
    return None


# ── Normalization ─────────────────────────────────────────────────────────────
def normalize_robot_density(value: float) -> float:
    return round(min(value / ROBOT_DENSITY_NORM_MAX * 100.0, 100.0), 1)


# ── Composite ─────────────────────────────────────────────────────────────────
def compute_composite(gen_ai: float | None, robot_norm: float | None) -> dict:
    available = []
    if gen_ai is not None:
        available.append(("gen_ai",    gen_ai,    WEIGHT_GEN_AI))
    if robot_norm is not None:
        available.append(("robot",     robot_norm, WEIGHT_ROBOT))
    if not available:
        return {"composite_score": None, "effective_weights": {}}
    total_w = sum(w for _, _, w in available)
    score   = sum(v * (w / total_w) for _, v, w in available)
    eff     = {k: round(w / total_w, 4) for k, _, w in available}
    return {"composite_score": round(score, 1), "effective_weights": eff}


def build_country_block(country: str) -> dict:
    gen_data   = GEN_AI_ADOPTION.get(country, {})
    robot_data = ROBOT_DENSITY.get(country, {})

    gen_val    = gen_data.get("value")
    robot_val  = robot_data.get("value")
    robot_norm = normalize_robot_density(robot_val) if robot_val is not None else None

    comp = compute_composite(gen_val, robot_norm)

    return {
        "composite_score":   comp["composite_score"],
        "effective_weights": comp["effective_weights"],
        "proxies": {
            # Key kept as "enterprise_adoption" for backward compatibility with UI
            "enterprise_adoption": {
                "raw_value":        gen_val,
                "unit":             "% of business decision-makers using gen AI",
                "normalized_score": round(float(gen_val), 1) if gen_val is not None else None,
                "coverage":         gen_data.get("coverage"),
                "survey_year":      gen_data.get("survey_year"),
                "note":             gen_data.get("note"),
            },
            "robot_density": {
                "raw_value":        robot_val,
                "unit":             "robots per 10,000 manufacturing workers",
                "normalized_score": robot_norm,
                "coverage":         robot_data.get("coverage"),
                "note":             robot_data.get("note"),
            },
        },
    }


def interpretive_sentence(us: float | None, cn: float | None) -> str:
    if us is None or cn is None:
        return "Insufficient data to compare adoption levels at this time."
    diff = us - cn
    if abs(diff) < 4:
        return (
            "U.S. and Chinese firms show broadly similar visible AI adoption "
            "levels on these proxies."
        )
    elif diff > 0:
        return (
            f"U.S. firms show stronger visible AI adoption on these proxies "
            f"(composite index gap: {diff:+.1f} points, US ahead)."
        )
    else:
        return (
            f"Chinese firms show stronger visible AI adoption on these proxies "
            f"(composite index gap: {abs(diff):.1f} points, China ahead). "
            f"China leads on both gen-AI adoption rate (SAS 2024: 83% vs 65%) "
            f"and industrial automation density (IFR 2024: 470 vs 295 robots/10K workers)."
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now = datetime.now(timezone.utc)

    # Try live OECD fetch for supplementary US context data
    oecd_live = fetch_oecd_us_ai_adoption()
    oecd_data = oecd_live if oecd_live is not None else OECD_FALLBACK_US

    us    = build_country_block("US")
    china = build_country_block("China")
    us_score = us["composite_score"]
    cn_score = china["composite_score"]

    output = {
        "dimension":   "adoption",
        "metric_key":  "ai_adoption_composite_index",
        "title":       "AI Adoption Index — U.S. vs China",
        "subtitle": (
            "Public proxies for AI adoption inside the U.S. and Chinese economies "
            "— not a complete measure of total usage."
        ),
        "description": (
            "A two-proxy composite index approximating economy-wide AI adoption. "
            "Combines gen-AI enterprise adoption rate (SAS/Coleman Parkes 2024 — "
            "the only directly comparable US-China survey available) with industrial "
            "automation density (IFR robot density). Neither proxy alone is a perfect "
            "measure; together they provide a transparent, country-comparable directional signal."
        ),
        "fetched_at":   now.isoformat(),
        "last_updated": now.isoformat(),
        "summary": {
            "US":    us,
            "China": china,
        },
        "interpretive_sentence": interpretive_sentence(us_score, cn_score),
        "composite_construction": {
            "method": (
                "Weighted average of normalized proxy scores. "
                "Gen-AI adoption is already 0–100 (% of decision-makers). "
                "Robot density is normalized as (value / 600) × 100. "
                "Weights: gen-AI adoption 60%, robot density 40%. "
                "If a proxy is unavailable for one country, the remaining "
                "proxy is re-weighted to 100% for that country."
            ),
            "weights": {
                "gen_ai_adoption": WEIGHT_GEN_AI,
                "robot_density":   WEIGHT_ROBOT,
            },
            "robot_density_normalization_reference": ROBOT_DENSITY_NORM_MAX,
        },
        "proxies_meta": {
            "gen_ai_adoption": GEN_AI_META,
            "robot_density":   ROBOT_DENSITY_META,
        },
        "supplementary_data": {
            "oecd_us_enterprise_ai": {
                "description": (
                    "OECD ICT Business survey: % of enterprises (≥10 employees) "
                    "using AI. Covers OECD members only — China not included. "
                    "Different and narrower definition than SAS gen-AI survey."
                ),
                "oecd_avg_or_us": oecd_data.get("value"),
                "is_oecd_average": oecd_data.get("is_average", False),
                "year":           oecd_data.get("year"),
                "source":         oecd_data.get("source"),
                "source_url":     oecd_data.get("source_url"),
                "live_fetch_ok":  oecd_live is not None,
                "note": oecd_data.get("note"),
            },
            "caict_china_manufacturing_ai": CAICT_CHINA_MFG,
        },
        "methodology_note": (
            "Primary source change from prior version: McKinsey State of AI (North "
            "America figure for US, estimated regional data for China) has been "
            "replaced by the SAS/Coleman Parkes 2024 global gen-AI survey, which "
            "is the only publicly available source that measured the same question "
            "in both the US and China using the same survey instrument. The prior "
            "McKinsey-based China estimate (70%) was indistinguishable from the US "
            "figure (72%), making that proxy unhelpful for US-China comparison. "
            "The SAS survey shows a clear directional gap: China 83% vs US 65%."
        ),
        "coverage_note": (
            "Gen-AI adoption (both countries): medium confidence — proprietary survey "
            "by SAS/Coleman Parkes; sample details only partially public. "
            "Robot density: high confidence — IFR uses identical methodology for all countries. "
            "Composite is valid for directional US-vs-China comparison; not a precise "
            "measurement of national AI adoption levels."
        ),
        "what_this_does_not_capture": [
            "Consumer AI usage (individuals using AI tools, apps, or devices)",
            "AI usage by small and medium enterprises not surveyed",
            "Private or unreported AI deployment (especially relevant for China)",
            "AI application quality or depth of integration",
            "Sector-specific AI adoption in financial services, healthcare, or government",
            "AI adoption by Chinese firms not covered in global surveys",
            "Distinction between AI-specific robotics and general industrial automation",
        ],
        "sources": [
            {
                "proxy":   "gen_ai_adoption",
                "name":    GEN_AI_META["source_name"],
                "url":     GEN_AI_META["source_url"],
                "edition": GEN_AI_META["edition"],
            },
            {
                "proxy":   "robot_density",
                "name":    ROBOT_DENSITY_META["source_name"],
                "url":     ROBOT_DENSITY_META["source_url"],
                "edition": ROBOT_DENSITY_META["edition"],
            },
            {
                "proxy":   "supplementary_us",
                "name":    "OECD ICT Access and Usage Database",
                "url":     "https://www.oecd.org/en/about/news/announcements/2026/01/ai-use-by-individuals-surges-across-the-oecd-as-adoption-by-firms-continues-to-expand.html",
                "edition": "January 2026 release (2025 data)",
            },
            {
                "proxy":   "supplementary_china",
                "name":    CAICT_CHINA_MFG["source"],
                "url":     CAICT_CHINA_MFG["source_url"],
                "edition": "March 2025 (2025 data)",
            },
        ],
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUTPUT_FILE}")
    print(f"  US composite:    {us_score}")
    print(f"  China composite: {cn_score}")
    if us_score is not None and cn_score is not None:
        gap    = abs(us_score - cn_score)
        leader = "US" if us_score > cn_score else "China"
        print(f"  Leader: {leader} (gap: {gap:.1f} points)")
    print(f"  OECD fetch: {'live' if oecd_live else 'fallback'} "
          f"({oecd_data.get('value')}% {'avg' if oecd_data.get('is_average') else 'US'}, "
          f"{oecd_data.get('year')})")


if __name__ == "__main__":
    main()
