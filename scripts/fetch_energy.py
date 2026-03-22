#!/usr/bin/env python3
"""
AI Energy Scaling Index — composite proxy for ability to sustain large-scale AI compute growth.

GOAL
  This is NOT a measure of total electricity generation.
  It measures: "How well can the US and China sustain large-scale AI compute growth?"

  Specifically:
    1. How fast is each country expanding electricity generation capacity?
    2. How much headroom exists in the grid before AI/data center demand becomes
       a constraint?
    3. How quickly can new power capacity reach data centers (grid connection speed)?

APPROACH
  Three curated proxies, combined into a weighted composite index (0–100).
  All reference data is drawn from publicly available, annually-updated sources.
  No live API calls — all values are curated constants, updated manually when
  source editions are published.

PROXY 1 — ELECTRICITY CAPACITY ADDITION RATE (40% weight)
  The annual rate at which each country is expanding its installed electricity
  generation capacity, expressed as a percentage of its existing installed base.
  Higher rate = faster energy supply growth = greater ability to meet rising
  AI/data center demand.

  Values (2023 data):
    US:    ~3.7%  — 46 GW added; 1,247 GW installed base (EIA Electric Power
                     Monthly January 2024; mostly utility-scale solar and wind)
    China: ~11.9% — 345 GW added; 2,900 GW installed base (IEA World Energy
                     Outlook 2024, China NEA 2023 annual report)

  Normalization: (rate / 15.0) × 100, capped at 100.
    15% reference: above any major economy's sustained growth rate, providing
    meaningful spread. China at ~12% scores ~79; US at ~3.7% scores ~25.

  Sources:
    US:    U.S. EIA, Electric Power Monthly (Jan 2024)
           https://www.eia.gov/electricity/monthly/
    China: IEA, World Energy Outlook 2024 (Oct 2024); China National Energy
           Administration (NEA) 2023 Annual Report

PROXY 2 — DATA CENTER POWER DEMAND HEADROOM (35% weight)
  Electricity consumed by data centers as a percentage of total national
  electricity generation, inverted to a "headroom" score. Lower DC share =
  more capacity available for future AI scaling = higher headroom score.

  Headroom formula: (HEADROOM_REF - dc_pct) / HEADROOM_REF × 100
    Where HEADROOM_REF = 10% (at 10% DC share, headroom = 0).

  Values (2023–2024 data):
    US:    ~4.8% DC share → headroom score 52.0
    China: ~2.5% DC share → headroom score 75.0

  Sources:
    IEA, Energy and AI (Jan 2025)
      https://www.iea.org/reports/energy-and-ai
    IEA, Electricity 2024 (Jan 2024)

  Notes:
    US data centers consumed ~200 TWh in 2023 (up from ~160 TWh in 2022);
    total US generation ~4,178 TWh (EIA 2023) → ~4.8%.
    China data centers consumed ~220 TWh in 2023; total generation ~8,900 TWh
    (NBS China 2023) → ~2.5%. China figure covers ICT broadly; AI-specific
    share is growing rapidly.

PROXY 3 — GRID CONNECTION SPEED SCORE (25% weight)
  A curated 0–100 score reflecting how quickly new electricity generation
  capacity can be connected to the grid and made available to data center
  operators. Combines interconnection queue depth, regulatory speed, and
  state capacity for infrastructure direction.

  Values:
    US:    30 / 100 — Severely constrained. LBNL 2024 reports 2,600+ GW of
                       generation waiting in interconnection queues, with a
                       median wait of 5+ years. FERC Order 2023 reforms are in
                       progress but have not yet cleared the backlog. Multiple
                       large-scale AI data center projects have been delayed by
                       grid connection timelines.
    China: 65 / 100 — State-directed permitting enables faster execution. The
                       National Development and Reform Commission (NDRC) can
                       approve large-scale projects on compressed timelines.
                       However, score is moderated from theoretical maximum by:
                       (a) renewable curtailment issues in some regions
                       (b) transmission bottlenecks between western generation
                       and eastern demand centers (partially addressed by
                       Ultra-High-Voltage transmission buildout)

  Sources:
    US:    Lawrence Berkeley National Laboratory (LBNL), "Queued Up: Characteristics
           of Power Plants Seeking Transmission Interconnection" (2024 edition)
           https://emp.lbl.gov/queues
           IEA, Energy and AI (Jan 2025) — notes US interconnection as key bottleneck
    China: IEA, Energy and AI (Jan 2025); China NDRC; IEA World Energy Outlook 2024

  Note: This is a qualitative-quantitative curated score, not derived from a
  single metric. It reflects the consensus view of multiple authoritative sources
  on relative grid connection speed and flexibility. Confidence: medium.

COMPOSITE CONSTRUCTION
  Composite = WEIGHT_CAPACITY × capacity_score
            + WEIGHT_HEADROOM × headroom_score
            + WEIGHT_GRID     × grid_score

  Capacity (40%) is weighted highest because it directly measures the rate of
  energy supply expansion — the most important factor for long-run AI scaling.
  Headroom (35%) captures near-term slack in the grid. Grid speed (25%) captures
  the infrastructure bottleneck that can prevent theoretical capacity from being
  practically available.

TO UPDATE REFERENCE DATA
  When new editions of source reports are published, update the relevant values
  in the proxy dicts below. Expected annual update cadence.

  Next expected updates:
    EIA Electric Power Monthly: monthly (annual capacity additions published ~Jan)
    IEA World Energy Outlook: ~October 2025
    IEA Energy and AI: irregular (next edition TBD)
    LBNL Queued Up: ~April–May 2025

Outputs to data/energy.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "energy.json"

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_CAPACITY = 0.40   # electricity capacity addition rate
WEIGHT_HEADROOM = 0.35   # data center power demand headroom
WEIGHT_GRID     = 0.25   # grid connection speed (curated score)

# ── Normalization references ──────────────────────────────────────────────────
CAPACITY_NORM_MAX  = 15.0   # % — no major economy sustains >15% annual growth
HEADROOM_NORM_REF  = 10.0   # % — at 10% DC share, headroom = 0 (fully pressured)

# ── Proxy 1: Electricity Capacity Addition Rate ───────────────────────────────
# Annual growth rate of installed electricity generation capacity (2023 data).
# Source: EIA Electric Power Monthly Jan 2024 (US); IEA WEO 2024 + China NEA (China)
#
# TO UPDATE: Change value, note, and edition when new annual data is published.
CAPACITY_ADDITION = {
    "US": {
        "value":     3.7,    # % annual growth (46 GW added / 1,247 GW base)
        "coverage":  "high",
        "note":      (
            "EIA Electric Power Monthly (Jan 2024) — 46 GW of utility-scale "
            "capacity added in 2023; installed base ~1,247 GW. Capacity mix: "
            "solar (~24 GW), storage (~10 GW), wind (~7 GW), gas (~4 GW)."
        ),
        "edition":   "2023 data (EIA Jan 2024)",
    },
    "China": {
        "value":     11.9,   # % annual growth (345 GW added / 2,900 GW base)
        "coverage":  "high",
        "note":      (
            "IEA World Energy Outlook 2024 + China NEA 2023 Annual Report — "
            "345 GW of new capacity commissioned in 2023; installed base ~2,900 GW. "
            "Driven by solar (~217 GW) and wind (~75 GW) additions. China has led "
            "global capacity additions every year since 2013."
        ),
        "edition":   "2023 data (IEA WEO 2024; China NEA 2023)",
    },
}

CAPACITY_ADDITION_META = {
    "source_name":    "EIA Electric Power Monthly (US); IEA World Energy Outlook 2024 + China NEA 2023 Annual Report (China)",
    "source_url":     "https://www.eia.gov/electricity/monthly/",
    "definition":     "Annual additions to installed electricity generation capacity as % of existing installed base (2023)",
    "update_cadence": "Annual — EIA publishes US capacity additions in Electric Power Monthly (~January); IEA WEO covers China annually (~October)",
}

# ── Proxy 2: Data Center Power Demand Headroom ───────────────────────────────
# Data center electricity consumption as % of total national generation,
# inverted to a headroom score. Source: IEA Energy and AI (Jan 2025).
#
# Headroom score = (HEADROOM_NORM_REF - dc_pct) / HEADROOM_NORM_REF * 100
# Reference: 10% — the point at which grid pressure becomes severe.
#
# TO UPDATE: Change value and edition when IEA publishes updated data center
#            consumption estimates.
DC_DEMAND = {
    "US": {
        "value":    4.8,    # % of total generation consumed by data centers (2023)
        "coverage": "high",
        "note":     (
            "IEA Energy and AI (Jan 2025) — US data centers consumed ~200 TWh "
            "in 2023 (up from ~160 TWh in 2022); total US generation ~4,178 TWh "
            "(EIA 2023). Share is rising: IEA projects US data center demand "
            "could exceed 500 TWh by 2030 under high-AI scenario."
        ),
        "edition":  "2023 data (IEA Energy and AI, Jan 2025)",
    },
    "China": {
        "value":    2.5,    # % of total generation consumed by data centers (2023)
        "coverage": "medium",
        "note":     (
            "IEA Energy and AI (Jan 2025) — China data centers consumed ~220 TWh "
            "in 2023; total generation ~8,900 TWh (NBS China 2023). China's "
            "lower share reflects its very large generation base. Demand is "
            "growing rapidly; figure covers all ICT workloads, not AI-specific. "
            "Confidence: medium — China data center statistics are less granular."
        ),
        "edition":  "2023 data (IEA Energy and AI, Jan 2025; NBS China 2023)",
    },
}

DC_DEMAND_META = {
    "source_name":    "IEA, Energy and AI (January 2025); EIA Electric Power Annual 2023 (US); NBS China Statistical Yearbook 2023 (China)",
    "source_url":     "https://www.iea.org/reports/energy-and-ai",
    "definition":     "Data center electricity consumption as % of total national electricity generation (2023). Inverted to headroom score: (10 - dc_share%) / 10 × 100.",
    "update_cadence": "Annual — IEA updates data center estimates in Energy and AI reports and Electricity publications",
}

# ── Proxy 3: Grid Connection Speed Score ─────────────────────────────────────
# Curated 0–100 score for how quickly new power capacity can be connected
# to the grid and made available to large-scale data center operators.
# Sources: LBNL Queued Up 2024 (US); IEA Energy and AI 2025; China NDRC/NEA.
#
# TO UPDATE: Review annually against LBNL Queued Up and IEA Energy reports.
#            US score may improve if FERC Order 2023 reforms reduce queue backlogs.
GRID_SPEED = {
    "US": {
        "value":    30,     # 0–100 curated score
        "coverage": "medium",
        "note":     (
            "LBNL Queued Up 2024 — 2,600+ GW of generation projects in US "
            "interconnection queues; median wait exceeds 5 years. Multiple "
            "large-scale AI data center projects face multi-year grid connection "
            "delays. FERC Order 2023 reforms in progress but backlog clearing "
            "will take years. Regulatory and permitting friction also significant "
            "(transmission siting, local approvals). Score: 30/100."
        ),
        "edition":  "2024 (LBNL Queued Up 2024; FERC Order 2023 status)",
    },
    "China": {
        "value":    65,     # 0–100 curated score
        "coverage": "medium",
        "note":     (
            "IEA Energy and AI 2025; China NDRC/NEA. State-directed permitting "
            "enables significantly faster execution for strategic infrastructure. "
            "NDRC can approve large-scale projects on compressed timelines. "
            "Score moderated from higher by: (a) renewable curtailment in some "
            "western regions; (b) transmission bottlenecks between generation "
            "centers (west) and demand centers (east), partially addressed by "
            "ongoing Ultra-High-Voltage (UHV) transmission buildout. Score: 65/100."
        ),
        "edition":  "2024 (IEA Energy and AI 2025; China NDRC 2024)",
    },
}

GRID_SPEED_META = {
    "source_name":    "LBNL Queued Up 2024 (US); IEA Energy and AI (Jan 2025) + China NDRC/NEA (China)",
    "source_url":     "https://emp.lbl.gov/queues",
    "definition":     "Curated 0–100 score for speed at which new generation capacity can be connected to the grid and used by data center operators. Confidence: medium.",
    "update_cadence": "Annual review — LBNL Queued Up publishes ~April–May; IEA Energy and AI irregular",
}


# ── Normalization ─────────────────────────────────────────────────────────────
def normalize_capacity(rate: float) -> float:
    return round(min(rate / CAPACITY_NORM_MAX * 100.0, 100.0), 1)

def normalize_headroom(dc_pct: float) -> float:
    score = (HEADROOM_NORM_REF - dc_pct) / HEADROOM_NORM_REF * 100.0
    return round(max(min(score, 100.0), 0.0), 1)

def normalize_grid(score: float) -> float:
    return round(float(score), 1)


# ── Composite ─────────────────────────────────────────────────────────────────
def compute_composite(cap: float | None, headroom: float | None, grid: float | None) -> dict:
    available = []
    if cap      is not None: available.append(("capacity_addition_rate", cap,      WEIGHT_CAPACITY))
    if headroom is not None: available.append(("dc_demand_headroom",     headroom,  WEIGHT_HEADROOM))
    if grid     is not None: available.append(("grid_connection_speed",  grid,      WEIGHT_GRID))

    if not available:
        return {"composite_score": None, "effective_weights": {}}

    total_weight = sum(w for _, _, w in available)
    composite    = sum(v * (w / total_weight) for _, v, w in available)
    eff_weights  = {k: round(w / total_weight, 4) for k, _, w in available}

    return {
        "composite_score":   round(composite, 1),
        "effective_weights": eff_weights,
    }


def build_country_block(country: str) -> dict:
    cap_data  = CAPACITY_ADDITION.get(country, {})
    dc_data   = DC_DEMAND.get(country, {})
    grid_data = GRID_SPEED.get(country, {})

    cap_val    = cap_data.get("value")
    dc_val     = dc_data.get("value")
    grid_val   = grid_data.get("value")

    cap_norm     = normalize_capacity(cap_val)   if cap_val  is not None else None
    headroom_norm = normalize_headroom(dc_val)   if dc_val   is not None else None
    grid_norm    = normalize_grid(grid_val)      if grid_val is not None else None

    comp = compute_composite(cap_norm, headroom_norm, grid_norm)

    return {
        "composite_score":   comp["composite_score"],
        "effective_weights": comp["effective_weights"],
        "proxies": {
            "capacity_addition_rate": {
                "raw_value":        cap_val,
                "unit":             "% annual capacity growth",
                "normalized_score": cap_norm,
                "coverage":         cap_data.get("coverage"),
                "note":             cap_data.get("note"),
            },
            "dc_demand_headroom": {
                "raw_value":        dc_val,
                "unit":             "% of grid (data centers)",
                "normalized_score": headroom_norm,
                "coverage":         dc_data.get("coverage"),
                "note":             dc_data.get("note"),
            },
            "grid_connection_speed": {
                "raw_value":        grid_val,
                "unit":             "/ 100 score",
                "normalized_score": grid_norm,
                "coverage":         grid_data.get("coverage"),
                "note":             grid_data.get("note"),
            },
        },
    }


def interpretive_sentence(us_score: float | None, cn_score: float | None) -> str:
    if us_score is None or cn_score is None:
        return "Insufficient data to compare AI energy scaling capacity at this time."
    diff = us_score - cn_score
    if abs(diff) < 4:
        return (
            "Energy capacity and constraints are mixed across both countries \u2014 "
            "no clear advantage in AI energy scaling capacity on these proxies."
        )
    elif diff > 0:
        return (
            f"The U.S. shows stronger capacity to support AI energy demand "
            f"on these proxies (composite gap: {diff:+.1f} points). "
            f"The U.S. leads on grid headroom and connection speed relative to current demand."
        )
    else:
        return (
            f"China shows stronger capacity to scale AI energy infrastructure "
            f"on these proxies (composite gap: {abs(diff):.1f} points, China ahead). "
            f"China\u2019s significantly faster electricity capacity addition rate "
            f"and lower grid demand pressure give it more runway to expand AI compute. "
            f"U.S. grid interconnection constraints are a material bottleneck."
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now   = datetime.now(timezone.utc)
    us    = build_country_block("US")
    china = build_country_block("China")

    us_score    = us["composite_score"]
    china_score = china["composite_score"]

    output = {
        "dimension":   "energy",
        "metric_key":  "ai_energy_scaling_index",
        "title":       "Energy & Power Constraints \u2014 AI Scaling Capacity",
        "subtitle": (
            "Composite proxy for each country\u2019s ability to sustain large-scale "
            "AI compute growth \u2014 not a measure of total electricity generation."
        ),
        "description": (
            "A three-proxy composite index measuring AI energy scaling capacity: "
            "electricity capacity addition rate (40%), data center power demand "
            "headroom (35%), and grid connection speed (25%). Higher score = "
            "greater ability to expand AI compute infrastructure without hitting "
            "energy supply or grid bottlenecks."
        ),
        "fetched_at":   now.isoformat(),
        "last_updated": now.isoformat(),
        "summary": {
            "US":    us,
            "China": china,
        },
        "interpretive_sentence": interpretive_sentence(us_score, china_score),
        "composite_construction": {
            "method": (
                f"Weighted average of three normalized proxy scores. "
                f"Capacity addition rate normalized as (rate / {CAPACITY_NORM_MAX}) \u00d7 100. "
                f"DC demand headroom as ({HEADROOM_NORM_REF} \u2212 dc_pct) / {HEADROOM_NORM_REF} \u00d7 100 "
                f"(inverted: lower demand share = more headroom = higher score). "
                f"Grid speed is a curated 0\u2013100 score. "
                f"Weights: capacity {WEIGHT_CAPACITY:.0%}, headroom {WEIGHT_HEADROOM:.0%}, "
                f"grid {WEIGHT_GRID:.0%}."
            ),
            "weights": {
                "capacity_addition_rate": WEIGHT_CAPACITY,
                "dc_demand_headroom":     WEIGHT_HEADROOM,
                "grid_connection_speed":  WEIGHT_GRID,
            },
            "normalization": {
                "capacity_norm_max":  CAPACITY_NORM_MAX,
                "headroom_norm_ref":  HEADROOM_NORM_REF,
                "grid_speed_range":   "0\u2013100 (curated)",
            },
        },
        "proxies_meta": {
            "capacity_addition_rate": CAPACITY_ADDITION_META,
            "dc_demand_headroom":     DC_DEMAND_META,
            "grid_connection_speed":  GRID_SPEED_META,
        },
        "methodology_note": (
            "This index measures AI energy scaling capacity \u2014 the ability to add "
            "power supply and connect it to data centers quickly \u2014 not total "
            "electricity generation or consumption. The capacity addition rate "
            "captures supply expansion speed; headroom captures near-term grid "
            "slack; grid connection speed captures the infrastructure bottleneck "
            "that determines whether theoretical capacity becomes practically available. "
            "A country with high generation but severe interconnection constraints "
            "will score lower than its raw capacity would suggest."
        ),
        "coverage_note": (
            "Capacity addition rate: high confidence (EIA/IEA annual publications). "
            "DC demand headroom: high confidence for US; medium for China (less granular "
            "data center statistics). Grid connection speed: medium confidence for both \u2014 "
            "this is a curated composite assessment, not a single verifiable metric."
        ),
        "what_this_does_not_capture": [
            "Total electricity generation or consumption",
            "Energy cost (electricity price per kWh, which affects AI ROI)",
            "Carbon intensity or renewable mix of AI-relevant power",
            "Nuclear power capacity expansion (US SMR pipeline; China nuclear buildout)",
            "Private or off-grid power arrangements for specific AI campuses",
            "Long-run transmission infrastructure adequacy (UHV lines, HVDC)",
            "Water availability constraints for data center cooling",
        ],
        "sources": [
            {
                "proxy":   "capacity_addition_rate",
                "name":    "U.S. EIA, Electric Power Monthly (January 2024)",
                "url":     "https://www.eia.gov/electricity/monthly/",
                "edition": "January 2024 (2023 data)",
            },
            {
                "proxy":   "capacity_addition_rate",
                "name":    "IEA, World Energy Outlook 2024",
                "url":     "https://www.iea.org/reports/world-energy-outlook-2024",
                "edition": "October 2024 (2023 data)",
            },
            {
                "proxy":   "dc_demand_headroom",
                "name":    "IEA, Energy and AI",
                "url":     "https://www.iea.org/reports/energy-and-ai",
                "edition": "January 2025",
            },
            {
                "proxy":   "grid_connection_speed",
                "name":    "LBNL, Queued Up: Characteristics of Power Plants Seeking Transmission Interconnection",
                "url":     "https://emp.lbl.gov/queues",
                "edition": "2024 edition",
            },
            {
                "proxy":   "grid_connection_speed",
                "name":    "IEA, Energy and AI",
                "url":     "https://www.iea.org/reports/energy-and-ai",
                "edition": "January 2025",
            },
        ],
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"Wrote {OUTPUT_FILE}")
    print(f"  US composite:    {us_score}")
    print(f"  China composite: {china_score}")
    if us_score is not None and china_score is not None:
        gap    = abs(us_score - china_score)
        leader = "US" if us_score > china_score else "China"
        print(f"  Leader: {leader} (gap: {gap:.1f} points)")


if __name__ == "__main__":
    main()
