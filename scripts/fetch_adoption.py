#!/usr/bin/env python3
"""
AI Adoption Index — composite proxy for economy-wide AI adoption.

APPROACH
  Builds a two-proxy composite index comparing US vs China on AI adoption,
  using publicly available, annually-updated reference data.

  Proxy 1 — Enterprise Adoption Rate (55% weight):
    The share of organizations actively using AI in at least one business
    function. Primary source: McKinsey "State of AI" 2025 (published May
    2025, covering 2024/2025 survey data). Cross-referenced with Stanford
    HAI AI Index 2025 (April 2025) which aggregates multiple surveys.
    North America figure used for US; best available China-region estimate
    used for China (see notes below).

  Proxy 2 — Industrial Automation Density (45% weight):
    Installed industrial robots per 10,000 manufacturing workers.
    Source: IFR (International Federation of Robotics) World Robotics 2024
    report (October 2024, covering 2023 operational data). Same methodology,
    same reporting body, directly country-comparable.

WHY A COMPOSITE INDEX
  No single public data source provides a clean, symmetric, and automatable
  measure of AI adoption in both the U.S. and Chinese economies:

  - Survey data (McKinsey, Stanford AI Index) has limited China-specific
    granularity and inconsistent sampling across countries.
  - Public filing data (SEC EDGAR) covers Chinese ADRs only — a tech-heavy
    sample that excludes Tencent, ByteDance, Huawei, and most Chinese firms.
  - Hard deployment metrics (robot density) are symmetric and verifiable
    but capture industrial automation broadly, not AI specifically.

  Together, these two proxies give a more rounded and honest picture than
  either alone, while keeping the methodology transparent and reproducible.

COMPOSITE CONSTRUCTION
  Normalization:
    - Enterprise adoption: already expressed as %; used directly (0–100).
    - Robot density: (value / ROBOT_DENSITY_NORM_MAX) × 100
      where ROBOT_DENSITY_NORM_MAX = 600 robots/10K workers
      (reference: above leading OECD economies ~430, well below South
      Korea's ~1,000 global outlier; gives headroom for China at ~470).

  Composite score = WEIGHT_ENTERPRISE × enterprise_norm
                  + WEIGHT_ROBOT      × robot_density_norm

  If a proxy is unavailable for one country, the missing proxy is excluded
  and the remaining proxy is re-weighted to 100% for that country.

TO UPDATE REFERENCE DATA
  When a new edition of a source is published, update the value(s) and the
  edition string in the ENTERPRISE_ADOPTION and ROBOT_DENSITY dicts below.
  The composite recalculates automatically.

  Next expected updates:
    - IFR World Robotics 2025: ~October 2025 (will cover 2024 data)
    - McKinsey State of AI 2026: ~May 2026
    - Stanford AI Index 2026: ~April 2026

Outputs to data/adoption.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "adoption.json"

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_ENTERPRISE = 0.55   # enterprise AI adoption survey
WEIGHT_ROBOT      = 0.45   # industrial robot density

# ── Robot density normalization reference ─────────────────────────────────────
# Updated to 600 robots/10K workers (was 500):
#   - OECD average is roughly 200–350 depending on year
#   - Germany ~429, Japan ~419 (IFR 2024)
#   - China ~470 (IFR 2024) — crowded the old 500 ceiling
#   - South Korea ~1,012 (global outlier, excluded as ceiling)
#   600 provides headroom above leading non-outlier economies while
#   keeping both US and China in meaningful, non-trivial score range.
ROBOT_DENSITY_NORM_MAX = 600.0

# ── Proxy 1: Enterprise AI Adoption Rate ─────────────────────────────────────
# Primary source: McKinsey & Company, "The State of AI" 2025 (May 2025)
# Cross-reference: Stanford HAI AI Index 2025 (April 2025)
# Definition: % of respondents' organizations using AI in at least one
#             business function
#
# Notes:
#   US figure: McKinsey 2025, North America respondents (~72%).
#     Global adoption rose to ~78% in 2025; North America slightly below
#     global average, consistent with the 2024 survey pattern.
#     Stanford AI Index 2025 corroborates high US adoption rates.
#     Confidence: high.
#
#   China figure: Estimated from McKinsey 2025 global/regional data and
#     CAICT (China Academy of Information and Communications Technology)
#     White Paper on China's AI Development (2024, published late 2024).
#     McKinsey does not break out China separately; ~70% reflects the
#     cross-referenced estimate from regional data and CAICT surveys on
#     large-enterprise adoption. Stanford AI Index 2025 shows China-based
#     respondents with broadly comparable adoption rates to North America.
#     Confidence: medium — treat as directional, not precise.
#
# TO UPDATE: Change value and edition when McKinsey or Stanford AI Index
#            publishes a new annual edition.
ENTERPRISE_ADOPTION = {
    "US": {
        "value":    72.0,   # percent
        "coverage": "high",
        "note":     (
            "McKinsey State of AI 2025 (May 2025), North America respondents; "
            "corroborated by Stanford HAI AI Index 2025 (April 2025)"
        ),
    },
    "China": {
        "value":    70.0,   # percent
        "coverage": "medium",
        "note":     (
            "Estimated from McKinsey State of AI 2025 global/regional data "
            "and CAICT AI White Paper 2024. McKinsey does not break out China "
            "separately; Stanford AI Index 2025 shows broadly comparable rates. "
            "Treat as directional."
        ),
    },
}

ENTERPRISE_ADOPTION_META = {
    "source_name":      "McKinsey & Company, The State of AI 2025",
    "source_url":       "https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai",
    "supplementary":    (
        "Stanford HAI AI Index 2025 (April 2025); "
        "CAICT White Paper on China's AI Development 2024 (China figure)"
    ),
    "edition":          "2025 (published May 2025)",
    "definition":       "% of organizations using AI in at least one business function",
    "update_cadence":   "Annual (McKinsey: typically May; Stanford AI Index: typically April)",
}

# ── Proxy 2: Industrial Robot Density ────────────────────────────────────────
# Source: International Federation of Robotics (IFR), World Robotics
# Edition: 2024 report (October 2024, covering 2023 operational data)
# Definition: Installed industrial robots per 10,000 manufacturing workers
#
# Notes:
#   - Highly symmetric: same source, same methodology, direct country-level data.
#   - China's continued rise reflects sustained "Made in China 2025" investment
#     in manufacturing automation across automotive, electronics, and precision
#     assembly. China overtook Japan and Germany in density ranking in 2023.
#   - Robot density captures industrial AI/automation broadly — not limited
#     to pure AI applications. A strength for cross-country comparability;
#     a limitation for AI-specificity.
#
# 2023 values (IFR World Robotics 2024, October 2024):
#   China: 470 robots/10K workers (up from 392 in 2022; overtook Japan/Germany)
#   US:    295 robots/10K workers (up from 274 in 2022)
#   For reference: South Korea ~1,012 (global outlier); Germany ~429; Japan ~419
#
# Previous values for reference:
#   China 2022: 392  |  US 2022: 274  (IFR World Robotics 2023)
#
# TO UPDATE: Change value and edition when IFR publishes a new annual report
#            (expected October 2025 for 2024 data).
ROBOT_DENSITY = {
    "US": {
        "value":    295,    # robots per 10,000 manufacturing workers
        "coverage": "high",
        "note":     "IFR World Robotics 2024 (2023 data), United States",
    },
    "China": {
        "value":    470,    # robots per 10,000 manufacturing workers
        "coverage": "high",
        "note":     (
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
    "update_cadence": "Annual (typically published in October)",
}


# ── Normalization ─────────────────────────────────────────────────────────────
def normalize_robot_density(value: float) -> float:
    """Normalize robot density to 0–100 scale against reference max."""
    return round(min(value / ROBOT_DENSITY_NORM_MAX * 100.0, 100.0), 1)


# ── Composite ─────────────────────────────────────────────────────────────────
def compute_composite(
    enterprise: float | None,
    robot_norm: float | None,
) -> dict:
    """
    Compute composite score from normalized proxy values.
    If one proxy is missing, re-weight the available proxy to 100%.
    Returns dict with composite_score and effective_weights used.
    """
    available = []
    if enterprise is not None:
        available.append(("enterprise", enterprise, WEIGHT_ENTERPRISE))
    if robot_norm is not None:
        available.append(("robot", robot_norm, WEIGHT_ROBOT))

    if not available:
        return {"composite_score": None, "effective_weights": {}}

    total_weight = sum(w for _, _, w in available)
    composite = sum(v * (w / total_weight) for _, v, w in available)
    eff_weights = {k: round(w / total_weight, 4) for k, _, w in available}

    return {
        "composite_score": round(composite, 1),
        "effective_weights": eff_weights,
    }


def build_country_block(country: str) -> dict:
    ent_data   = ENTERPRISE_ADOPTION.get(country, {})
    robot_data = ROBOT_DENSITY.get(country, {})

    ent_value   = ent_data.get("value")
    robot_value = robot_data.get("value")
    robot_norm  = normalize_robot_density(robot_value) if robot_value is not None else None

    comp = compute_composite(ent_value, robot_norm)

    return {
        "composite_score":   comp["composite_score"],
        "effective_weights": comp["effective_weights"],
        "proxies": {
            "enterprise_adoption": {
                "raw_value":        ent_value,
                "unit":             "% organizations using AI",
                "normalized_score": round(float(ent_value), 1) if ent_value is not None else None,
                "coverage":         ent_data.get("coverage"),
                "note":             ent_data.get("note"),
            },
            "robot_density": {
                "raw_value":        robot_value,
                "unit":             "robots per 10,000 manufacturing workers",
                "normalized_score": robot_norm,
                "coverage":         robot_data.get("coverage"),
                "note":             robot_data.get("note"),
            },
        },
    }


def interpretive_sentence(us_score: float | None, cn_score: float | None) -> str:
    if us_score is None or cn_score is None:
        return "Insufficient data to compare adoption levels at this time."
    diff = us_score - cn_score
    if abs(diff) < 4:
        return (
            "U.S. and Chinese firms and institutions show broadly similar "
            "visible AI adoption levels on these proxies."
        )
    elif diff > 0:
        return (
            f"U.S. firms and institutions show stronger visible AI adoption "
            f"on these proxies (composite index gap: {diff:+.1f} points). "
            f"The U.S. leads on both enterprise survey adoption and automation density."
        )
    else:
        return (
            f"Chinese firms and institutions show stronger visible AI adoption "
            f"on these proxies — driven primarily by higher industrial automation "
            f"density in manufacturing. Enterprise survey adoption rates are more "
            f"comparable between the two countries "
            f"(composite index gap: {abs(diff):.1f} points, China ahead)."
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now = datetime.now(timezone.utc)

    us    = build_country_block("US")
    china = build_country_block("China")

    us_score = us["composite_score"]
    cn_score = china["composite_score"]

    output = {
        "dimension":   "adoption",
        "metric_key":  "ai_adoption_composite_index",
        "title":       "AI Adoption Index — U.S. vs China",
        "subtitle":    (
            "Public proxies for AI adoption inside the U.S. and Chinese economies "
            "— not a complete measure of total usage."
        ),
        "description": (
            "A two-proxy composite index approximating economy-wide AI adoption. "
            "Combines enterprise AI adoption rates (survey-based, McKinsey 2024) "
            "with industrial automation density (IFR robot density, 2022 data). "
            "Neither proxy alone is a perfect measure of AI usage; together they "
            "provide a transparent, country-comparable directional signal."
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
                "Enterprise adoption is already 0-100 (% of organizations). "
                "Robot density is normalized as (value / 500) x 100 where "
                "500 robots/10K workers is the normalization reference point. "
                "Default weights: enterprise 55%, robot density 45%. "
                "If a proxy is unavailable for one country, the remaining "
                "proxy is re-weighted to 100%."
            ),
            "weights": {
                "enterprise_adoption": WEIGHT_ENTERPRISE,
                "robot_density":       WEIGHT_ROBOT,
            },
            "robot_density_normalization_reference": ROBOT_DENSITY_NORM_MAX,
        },
        "proxies_meta": {
            "enterprise_adoption": ENTERPRISE_ADOPTION_META,
            "robot_density":       ROBOT_DENSITY_META,
        },
        "methodology_note": (
            "This index uses a multi-proxy approach because no single public data "
            "source provides a clean, symmetric, and automatable measure of AI adoption "
            "in both the U.S. and Chinese economies. The enterprise survey proxy "
            "(McKinsey) covers large firms and is comparable in intent but has limited "
            "China-specific granularity. The robot density proxy (IFR) is highly "
            "symmetric and verifiable but measures industrial automation broadly, not "
            "AI specifically. The composite score is a transparent, directional proxy "
            "— not a definitive measure of national AI adoption."
        ),
        "coverage_note": (
            "Enterprise adoption (China): estimated from regional McKinsey data and "
            "CAICT surveys — confidence is medium; treat as directional. "
            "Robot density: high confidence for both countries — IFR uses the same "
            "methodology and reporting framework for all countries. "
            "Composite is valid for directional U.S.-vs-China comparison."
        ),
        "what_this_does_not_capture": [
            "Consumer AI usage (individuals using AI tools, apps, or devices)",
            "AI usage by small and medium enterprises",
            "Private or unreported AI deployment",
            "AI application quality or depth of integration",
            "Software-only AI deployments not captured in industrial robot density",
            "Sector-specific AI adoption in financial services, healthcare, or services",
            "AI adoption among Chinese firms that do not file with the SEC",
        ],
        "sources": [
            {
                "proxy":   "enterprise_adoption",
                "name":    ENTERPRISE_ADOPTION_META["source_name"],
                "url":     ENTERPRISE_ADOPTION_META["source_url"],
                "edition": ENTERPRISE_ADOPTION_META["edition"],
            },
            {
                "proxy":   "robot_density",
                "name":    ROBOT_DENSITY_META["source_name"],
                "url":     ROBOT_DENSITY_META["source_url"],
                "edition": ROBOT_DENSITY_META["edition"],
            },
        ],
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"Wrote {OUTPUT_FILE}")
    print(f"  US composite:    {us_score}")
    print(f"  China composite: {cn_score}")
    if us_score is not None and cn_score is not None:
        gap    = abs(us_score - cn_score)
        leader = "US" if us_score > cn_score else "China"
        print(f"  Leader: {leader} (gap: {gap:.1f} points)")


if __name__ == "__main__":
    main()
