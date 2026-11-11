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
    4. How favorable are energy costs and power access for AI data center operators?

APPROACH
  Four curated proxies, combined into a weighted composite index (0–100).
  All reference data is drawn from publicly available, annually-updated sources.
  No live API calls — all values are curated constants, updated manually when
  source editions are published.

IMPORTANT DISTINCTION: TOTAL CAPACITY vs. AI-USABLE POWER
  National electricity capacity addition rate measures how fast the grid is growing,
  but not all new capacity is equally useful for AI data centers:
  - Solar (25–30% capacity factor) and wind (30–45%) are intermittent; AI clusters
    run 24/7 and need firm, dispatchable power.
  - Nuclear, gas, hydro, and battery storage provide firm power.
  - China's 2024 additions were ~58% solar/wind; these are real capacity gains but
    require storage or backup to serve 24/7 AI workloads reliably.
  - The US additions were also mostly solar (~60%) with growing storage deployment.
  This limitation is noted in the methodology but NOT adjusted in the normalized score —
  the raw addition rate is still the best available annual-cadence signal for long-run
  energy supply expansion. Future editions may apply a capacity-factor weight.

PROXY 1 — ELECTRICITY CAPACITY ADDITION RATE (30% weight)
  The annual rate at which each country is expanding its installed electricity
  generation capacity, expressed as a percentage of its existing installed base.
  Higher rate = faster energy supply growth = greater ability to meet rising AI demand.

  Values (2024 data):
    US:    ~4.8% — ~60 GW added; ~1,250 GW installed base.
                    EIA Electric Power Monthly (2025); solar-dominated additions.
    China: ~13.1% — ~380 GW added; ~2,900 GW base.
                    IEA Renewables 2024; China NEA 2024. Record solar year (≥280 GW solar).

  Weight reduced from 40% to 30% (previous version) to partially account for the
  intermittency caveat above — raw additions slightly overstate AI-usable capacity.

  Normalization: (rate / 15.0) × 100, capped at 100.

PROXY 2 — DATA CENTER POWER DEMAND HEADROOM (25% weight)
  Electricity consumed by data centers as % of total national generation, inverted
  to a headroom score. Lower DC share = more capacity available for future AI
  scaling = higher headroom score.

  Headroom formula: (10.0 − dc_pct) / 10.0 × 100  (reference: 10% = severely pressured)

  Values (2024 data, updated from IEA Energy and AI / Electricity 2025):
    US:    ~6.2% DC share → headroom 38.0
           DC demand ~260 TWh; total generation ~4,200 TWh (EIA 2024 estimate).
           Rising rapidly: IEA projects 500+ TWh by 2030 in high-AI scenario.
    China: ~2.6% DC share → headroom 74.0
           DC demand ~250 TWh; total generation ~9,500 TWh (NBS China 2024).
           Lower share reflects very large generation base, not lower DC demand.

  Note: This metric is increasingly asymmetric — the US share is growing fast as
  AI cluster buildout accelerates. The headroom score will compress for the US
  over 2025–2028. China's very large generation base provides more buffer.

PROXY 3 — GRID CONNECTION SPEED (25% weight)
  A curated 0–100 score reflecting how quickly new electricity generation capacity
  can be connected to the grid and made available to data center operators.

  Values (2024–2025):
    US:    30 / 100 — LBNL Queued Up 2025: 2,600+ GW in queues; median wait >5 years.
                       FERC Order 2023 reforms in progress; backlog clearing is slow.
                       Virginia and Texas face acute capacity constraints from AI DC boom.
    China: 65 / 100 — NDRC/NEA state-directed permitting enables compressed timelines
                       for priority infrastructure. Partially offset by: (a) renewable
                       curtailment in western provinces; (b) west-to-east transmission
                       gap partially addressed by ongoing UHV network buildout.

  Score is a curated composite assessment (confidence: medium).

PROXY 4 — ENERGY COST & DC POWER ACCESS (20% weight)
  A curated 0–100 score for how favorable the electricity cost environment is
  for large-scale AI data center operators. Combines:
    — Industrial electricity price (lower = better AI ROI on compute)
    — PPA market depth (long-term Power Purchase Agreement availability)
    — Government / utility DC siting support and special rate programs

  Values (2024–2025):
    US:    50 / 100 — Industrial electricity ~7.7 cents/kWh avg (EIA 2024), rising
                       with AI demand surge. Good PPA market: hyperscalers execute
                       multi-GW PPAs at 3.5–6 cents/kWh in best markets (Texas,
                       Pacific NW, Midwest). IRA clean energy credits benefit large
                       operators. Demand competition is bidding up prices and grid
                       connection fees in key markets (Virginia, N. Virginia, Texas).
    China: 65 / 100 — National industrial electricity ~7.5 cents/kWh (NBS 2024,
                       exchange rate adjusted). Significant advantage in designated
                       AI computing zones: Inner Mongolia, Xinjiang, Guizhou, Sichuan
                       offer 2–4 cents/kWh for computing facilities. East Data West
                       Compute (EDWC/东数西算) program provides structured preferential
                       rates and land allocation. Government-directed incentive programs.
                       Offset by: regional reliability variation (renewable curtailment
                       in some western zones); east–west transmission costs that
                       partially offset zone price advantages for eastern data consumers.

  Source: EIA Annual Energy Outlook 2025 (US prices); China NBS 2024 / NDRC EDWC policy
          documents (China prices); various hyperscaler and DC operator disclosures.
  Confidence: medium for both — retail/industrial prices differ from actual contracted
  rates for large operators; actual PPA terms are commercially sensitive.

SUPPLEMENTARY — AI DATA CENTER PIPELINE (not scored)
  Announced/under-construction AI data center capacity (2024–2026 pipeline).
  Included as context only — not in the composite score.

    US:    ~60–80 GW equivalent committed across Microsoft, Google, Amazon, Meta
           (hyperscaler CapEx announcements totaling $300B+ for 2025).
    China: ~30–50 GW equivalent across Alibaba, ByteDance, Tencent, Huawei Cloud,
           EDWC national nodes. Exact figures less publicly disclosed.

  Note: These figures reflect announced investment/siting plans, not operational
  capacity. Actual MW online may diverge significantly.

COMPOSITE CONSTRUCTION
  Composite = WEIGHT_CAPACITY × capacity_score
            + WEIGHT_HEADROOM × headroom_score
            + WEIGHT_GRID     × grid_score
            + WEIGHT_ENERGY_COST × energy_cost_score

  Capacity (30%) measures long-run supply expansion.
  Headroom (25%) captures near-term grid slack for additional AI load.
  Grid speed (25%) captures whether capacity can reach data centers.
  Energy cost (20%) captures economic feasibility of AI compute at scale.

TO UPDATE REFERENCE DATA
  When new editions of source reports are published, update the relevant values below.
  Expected annual update cadence.

  Next expected updates:
    EIA Electric Power Monthly: monthly (capacity additions ~Jan/Feb)
    IEA World Energy Outlook: ~October 2025
    IEA Energy and AI: irregular (watch for 2025 update)
    LBNL Queued Up: ~April–May 2025
    EIA Annual Energy Outlook: ~February 2026

Outputs to data/energy.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "energy.json"

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_CAPACITY    = 0.30   # electricity capacity addition rate
WEIGHT_HEADROOM    = 0.25   # data center power demand headroom
WEIGHT_GRID        = 0.25   # grid connection speed (curated score)
WEIGHT_ENERGY_COST = 0.20   # energy cost & DC power access (curated score)

# ── Normalization references ──────────────────────────────────────────────────
CAPACITY_NORM_MAX  = 15.0   # % — no major economy sustains >15% annual growth
HEADROOM_NORM_REF  = 10.0   # % — at 10% DC share, headroom = 0 (fully pressured)

# ── Proxy 1: Electricity Capacity Addition Rate ───────────────────────────────
# Updated to 2024 data.
# US: EIA Electric Power Monthly (Feb 2025) — ~60 GW additions; ~1,250 GW base
# China: IEA Renewables 2024 + China NEA 2024 Annual Report — ~380 GW additions
CAPACITY_ADDITION = {
    "US": {
        "value":     4.8,    # % annual growth (60 GW / 1,250 GW base)
        "coverage":  "high",
        "note": (
            "EIA Electric Power Monthly (Feb 2025) — approximately 60 GW of "
            "utility-scale capacity added in 2024; installed base ~1,250 GW. "
            "Capacity mix: solar (~35 GW), battery storage (~18 GW), wind (~7 GW). "
            "Caveat: ~80% of 2024 additions were variable renewable (solar/wind); "
            "AI data centers require firm 24/7 power and rely on gas/nuclear for "
            "baseload. Battery storage deployment is increasing but does not yet "
            "provide multi-day firm capacity."
        ),
        "edition":   "2024 data (EIA Feb 2025)",
        "capacity_mix_note": "~60% variable renewables, ~30% storage, ~10% firm (gas/nuclear/hydro)",
    },
    "China": {
        "value":     13.1,   # % annual growth (380 GW / 2,900 GW base)
        "coverage":  "high",
        "note": (
            "IEA Renewables 2024 + China NEA 2024 Annual Report — ~380 GW commissioned "
            "in 2024; installed base ~2,900 GW. Driven by record solar (~280 GW) and "
            "wind (~80 GW) additions. China installed more solar in 2024 than the rest "
            "of the world combined. Caveat: ~95% of additions are variable renewable; "
            "coal and pumped hydro provide baseload stability but curtailment rates "
            "remain elevated in western regions (Inner Mongolia, Xinjiang, Gansu). "
            "Battery storage additions also at record levels (~65 GW)."
        ),
        "edition":   "2024 data (IEA Renewables 2024; China NEA 2024)",
        "capacity_mix_note": "~95% variable renewables; firm power from coal/hydro base fleet",
    },
}

CAPACITY_ADDITION_META = {
    "source_name":    "EIA Electric Power Monthly Feb 2025 (US); IEA Renewables 2024 + China NEA 2024 Annual Report (China)",
    "source_url":     "https://www.eia.gov/electricity/monthly/",
    "source_url_china": "https://www.iea.org/reports/renewables-2024",
    "definition":     "Annual additions to installed electricity generation capacity as % of existing installed base (2024)",
    "caveat":         "Raw addition rate includes variable renewables (solar/wind) which have 25–45% capacity factors. AI data centers need 24/7 firm power. Score slightly overstates AI-usable capacity expansion, especially for China where >95% of additions are variable.",
    "update_cadence": "Annual — EIA Electric Power Monthly publishes capacity additions ~Feb; IEA WEO and China NEA report ~October/November",
}

# ── Proxy 2: Data Center Power Demand Headroom ───────────────────────────────
# Updated to 2024 estimates. US DC demand rising faster than China's (% of grid).
# Source: IEA Energy and AI (Jan 2025); IEA Electricity 2025; EIA / NBS China.
DC_DEMAND = {
    "US": {
        "value":    6.2,    # % of total generation consumed by data centers (2024 est.)
        "coverage": "high",
        "note": (
            "IEA Energy and AI (Jan 2025) + IEA Electricity 2025 — US data centers "
            "consumed ~260 TWh in 2024 (up from ~200 TWh in 2023); total US generation "
            "~4,200 TWh (EIA 2024 estimate). DC share rising rapidly: IEA projects "
            "US DC demand could reach 500+ TWh by 2030 under high-AI scenario, pushing "
            "share above 11–12% and fully consuming current headroom. Virginia data center "
            "corridor and Texas AI clusters are already straining local grid capacity."
        ),
        "edition":  "2024 est. (IEA Energy and AI Jan 2025; EIA)",
    },
    "China": {
        "value":    2.6,    # % of total generation consumed by data centers (2024 est.)
        "coverage": "medium",
        "note": (
            "IEA Energy and AI (Jan 2025) — China data centers consumed ~250 TWh "
            "in 2024; total generation ~9,500 TWh (NBS China 2024 estimate). "
            "China's lower share reflects its very large generation base. "
            "AI-specific DC demand is growing rapidly but is a smaller fraction of "
            "total than in the US. Figure covers all ICT workloads; AI share is a subset. "
            "Confidence: medium — China data center statistics less granular than US."
        ),
        "edition":  "2024 est. (IEA Energy and AI Jan 2025; NBS China 2024)",
    },
}

DC_DEMAND_META = {
    "source_name":    "IEA Energy and AI (Jan 2025); IEA Electricity 2025; EIA (US); NBS China Statistical Yearbook 2024 (China)",
    "source_url":     "https://www.iea.org/reports/energy-and-ai",
    "definition":     "Data center electricity consumption as % of total national electricity generation (2024 estimate). Inverted to headroom: (10 − dc_share%) / 10 × 100. At 10% share, headroom = 0.",
    "ai_context":     "US headroom is compressing fast — the 2024 value of 6.2% is up from 4.8% in 2023. At current AI buildout pace, US headroom hits zero around 2028–2030. China's large generation base provides significantly more buffer.",
    "update_cadence": "Annual — IEA Energy and AI; IEA Electricity 2025 track DC demand",
}

# ── Proxy 3: Grid Connection Speed Score ─────────────────────────────────────
# Curated 0–100 score. Assesses three sub-factors:
#   (a) Interconnection queue depth and wait time
#   (b) Regulatory and permitting speed
#   (c) State/national capacity to direct infrastructure siting
# Sources: LBNL Queued Up 2025 (US); IEA Energy and AI 2025; China NDRC/NEA.
GRID_SPEED = {
    "US": {
        "value":    30,     # 0–100 curated score
        "coverage": "medium",
        "sub_factors": {
            "queue_depth":       "LBNL Queued Up 2025: 2,600+ GW in queues; median wait >5 years. Score: 15/100.",
            "regulatory_speed":  "FERC Order 2023 reforms underway but not yet clearing backlog. Transmission siting (state-level, NIMBYism) major constraint. Score: 30/100.",
            "siting_authority":  "No federal AI infrastructure siting authority. Data center projects face local zoning, water rights, utility territory constraints. Score: 45/100.",
        },
        "note": (
            "LBNL Queued Up 2025 — 2,600+ GW of generation projects in US "
            "interconnection queues; median wait exceeds 5 years. Multiple "
            "large-scale AI data center projects face multi-year grid connection "
            "delays (reported in Virginia, Texas, and other AI cluster markets). "
            "FERC Order 2023 (cluster-based interconnection reform) is in progress; "
            "the backlog will take years to clear. Water and permitting constraints "
            "add to effective delays. Score reflects structural constraint, not "
            "isolated incidents."
        ),
        "edition":  "2025 (LBNL Queued Up 2025; FERC Order 2023 status)",
    },
    "China": {
        "value":    65,     # 0–100 curated score
        "coverage": "medium",
        "sub_factors": {
            "queue_depth":       "No published queue data; NDRC/NEA approvals for priority projects can be compressed. Score: 75/100.",
            "regulatory_speed":  "State-directed permitting enables compressed timelines for strategic AI infrastructure. EDWC program provides pre-approved sites. Score: 80/100.",
            "siting_authority":  "Central-provincial coordination enables land/grid reservation for computing hubs. Score: 75/100.",
        },
        "note": (
            "China NDRC/NEA + IEA Energy and AI 2025 — State-directed permitting "
            "enables significantly faster execution for strategic infrastructure. "
            "NDRC/NEA designate 8 national computing power hub nodes under the East "
            "Data West Compute program, with pre-negotiated grid connections and "
            "preferential power pricing. Score moderated from higher by: "
            "(a) renewable curtailment in western provinces (Inner Mongolia, Xinjiang) "
            "means data centers sited for cheap power may face reliability issues; "
            "(b) west-to-east transmission gap — UHV buildout addresses this but "
            "transmission costs partially offset western zone price advantage; "
            "(c) reliability data for eastern AI clusters less transparent."
        ),
        "edition":  "2025 (IEA Energy and AI 2025; China NDRC; China NEA)",
    },
}

GRID_SPEED_META = {
    "source_name":    "LBNL Queued Up 2025 (US); IEA Energy and AI Jan 2025 + China NDRC/NEA (China)",
    "source_url":     "https://emp.lbl.gov/queues",
    "source_url_iea": "https://www.iea.org/reports/energy-and-ai",
    "definition":     "Curated 0–100 score for speed at which new generation capacity can be connected to the grid and made available to large-scale data center operators. Sub-factors: interconnection queue depth, regulatory/permitting speed, and national siting authority.",
    "confidence":     "Medium — curated composite assessment, not a single verifiable metric. Scores reflect consensus of cited sources on relative infrastructure execution speed.",
    "update_cadence": "Annual review — LBNL Queued Up publishes ~April–May; IEA Energy and AI irregular",
}

# ── Proxy 4: Energy Cost & DC Power Access ───────────────────────────────────
# NEW in v2. Curated 0–100 score combining:
#   (a) Industrial electricity price (lower = better for AI ROI)
#   (b) PPA market depth (long-term Power Purchase Agreement availability)
#   (c) Government/utility support for AI data center siting and pricing
#
# Note: This proxy captures economic feasibility of scaling AI compute, complementing
# the physical grid metrics above. A country can have abundant power but high prices
# (bad for AI ROI) or cheap power with poor reliability (bad for 24/7 AI workloads).
ENERGY_COST = {
    "US": {
        "value":         50,     # 0–100 curated score
        "coverage":      "medium",
        "industrial_electricity_cents_kwh": 7.7,   # EIA 2024 average
        "ppa_market_depth": "deep",
        "note": (
            "EIA Annual Energy Outlook 2025 — US industrial electricity averaged "
            "~7.7 cents/kWh in 2024, rising 8% year-over-year as AI data center "
            "demand increases. PPA market is deep: hyperscalers execute multi-GW "
            "contracts at 3.5–6 cents/kWh in best markets (Pacific NW hydro/wind, "
            "Texas wind, Midwest solar). IRA clean energy credits improve economics "
            "for operators buying clean power. Offset by: rising grid connection "
            "fees and congestion charges in AI cluster markets (N. Virginia, Texas); "
            "electricity price competition from data center buildout is a noted risk. "
            "Score: 50/100 — good optionality for large operators; rising pressure."
        ),
        "edition": "2024 (EIA Annual Energy Outlook 2025; hyperscaler PPA disclosures)",
    },
    "China": {
        "value":         65,     # 0–100 curated score
        "coverage":      "medium",
        "industrial_electricity_cents_kwh": 7.5,   # NBS China 2024 (national avg, exchange-rate adjusted)
        "dc_zone_electricity_cents_kwh":    3.5,   # EDWC hub zones (Inner Mongolia, Xinjiang, Guizhou)
        "ppa_market_depth": "moderate (state-directed)",
        "note": (
            "NBS China Statistical Yearbook 2024 + NDRC East Data West Compute policy "
            "documents — National industrial electricity ~7.5 cents/kWh (comparable "
            "to US average). Significant advantage in national computing hub zones: "
            "Inner Mongolia, Xinjiang, Guizhou, Sichuan offer ~2–4 cents/kWh to "
            "qualifying computing facilities under NDRC-approved programs. "
            "Government-directed 东数西算 (East Data West Compute) policy provides "
            "structured access to cheap western power for eastern AI workloads. "
            "Offset by: (a) west-to-east transmission costs partially erode zone "
            "advantage for operators serving eastern users; (b) renewable curtailment "
            "in cheapest zones may require backup power arrangements; (c) price "
            "transparency is lower than US market. Score: 65/100 — meaningful "
            "structural cost advantage, especially for operators willing to site "
            "in NDRC-designated zones."
        ),
        "edition": "2024 (NBS China 2024; NDRC EDWC policy 2022–2024)",
    },
}

ENERGY_COST_META = {
    "source_name":       "EIA Annual Energy Outlook 2025 (US); NBS China 2024 + NDRC EDWC policy documents (China)",
    "source_url":        "https://www.eia.gov/outlooks/aeo/",
    "source_url_china":  "http://www.ndrc.gov.cn/",
    "definition":        "Curated 0–100 score combining: industrial electricity price (lower = better), PPA market depth (higher = better optionality), and government/utility DC siting support. Reflects economic feasibility of AI compute scale-up, not just physical power availability.",
    "confidence":        "Medium — retail/industrial prices differ from actual contracted rates for large operators; PPA terms are commercially sensitive; Chinese zone pricing requires qualification.",
    "update_cadence":    "Annual — EIA Annual Energy Outlook; NBS China Statistical Yearbook; NDRC policy announcements",
}

# ── Supplementary: AI Data Center Pipeline ───────────────────────────────────
# NOT scored — included as context only.
AI_DC_PIPELINE = {
    "US": {
        "announced_gw_est": 70,
        "note": (
            "Hyperscaler AI data center commitments 2024–2026: Microsoft, Google, "
            "Amazon, Meta have announced combined CapEx exceeding $300B for 2025 "
            "data center expansion. Using ~1 MW per $4M invested as rough density "
            "estimate, this implies ~70–80 GW of capacity announcements. Actual "
            "delivery pace constrained by grid connection timelines and permitting. "
            "Key clusters: Northern Virginia, Texas, Arizona, Georgia, Midwest."
        ),
        "confidence": "Low — announced ≠ operational; delivery timelines uncertain",
    },
    "China": {
        "announced_gw_est": 40,
        "note": (
            "Chinese tech company AI data center commitments 2024–2026: Alibaba, "
            "ByteDance, Tencent, Huawei Cloud + EDWC national node buildout. "
            "NDRC targets 10 million racks of computing capacity by 2025; equivalent "
            "to ~40–50 GW depending on rack density assumptions. Less publicly "
            "disclosed than US counterparts; figures are estimated from policy "
            "documents and media reports. Key clusters: Inner Mongolia, Guangdong, "
            "Chengdu, Yangtze River Delta corridor."
        ),
        "confidence": "Low — Chinese tech companies less publicly transparent on DC pipeline; NDRC targets are policy goals not commitments",
    },
    "methodology_note": (
        "AI data center pipeline is included as context but not in the composite score "
        "because: (a) announced capacity often exceeds what is actually built on schedule; "
        "(b) grid connection delays mean announced capacity and available power can diverge "
        "by years; (c) comparing government-policy targets (China) to private commitments "
        "(US) is methodologically inconsistent. See the Investment dimension for related data."
    ),
}


# ── Normalization ─────────────────────────────────────────────────────────────
def normalize_capacity(rate: float) -> float:
    return round(min(rate / CAPACITY_NORM_MAX * 100.0, 100.0), 1)

def normalize_headroom(dc_pct: float) -> float:
    score = (HEADROOM_NORM_REF - dc_pct) / HEADROOM_NORM_REF * 100.0
    return round(max(min(score, 100.0), 0.0), 1)

def normalize_grid(score: float) -> float:
    return round(float(score), 1)

def normalize_energy_cost(score: float) -> float:
    return round(float(score), 1)


# ── Composite ─────────────────────────────────────────────────────────────────
def compute_composite(cap: float | None, headroom: float | None,
                      grid: float | None, energy_cost: float | None) -> dict:
    slots = [
        ("capacity_addition_rate", cap,         WEIGHT_CAPACITY),
        ("dc_demand_headroom",     headroom,     WEIGHT_HEADROOM),
        ("grid_connection_speed",  grid,         WEIGHT_GRID),
        ("energy_cost_access",     energy_cost,  WEIGHT_ENERGY_COST),
    ]
    available = [(k, v, w) for k, v, w in slots if v is not None]
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
    cap_data    = CAPACITY_ADDITION.get(country, {})
    dc_data     = DC_DEMAND.get(country, {})
    grid_data   = GRID_SPEED.get(country, {})
    cost_data   = ENERGY_COST.get(country, {})

    cap_val    = cap_data.get("value")
    dc_val     = dc_data.get("value")
    grid_val   = grid_data.get("value")
    cost_val   = cost_data.get("value")

    cap_norm    = normalize_capacity(cap_val)   if cap_val   is not None else None
    headroom_norm = normalize_headroom(dc_val)  if dc_val    is not None else None
    grid_norm   = normalize_grid(grid_val)      if grid_val  is not None else None
    cost_norm   = normalize_energy_cost(cost_val) if cost_val is not None else None

    comp = compute_composite(cap_norm, headroom_norm, grid_norm, cost_norm)

    d: dict = {
        "composite_score":   comp["composite_score"],
        "effective_weights": comp["effective_weights"],
        "proxies": {
            "capacity_addition_rate": {
                "raw_value":        cap_val,
                "unit":             "% annual capacity growth",
                "normalized_score": cap_norm,
                "coverage":         cap_data.get("coverage"),
                "capacity_mix_note": cap_data.get("capacity_mix_note"),
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
                "sub_factors":      grid_data.get("sub_factors"),
                "note":             grid_data.get("note"),
            },
            "energy_cost_access": {
                "raw_value":        cost_val,
                "unit":             "/ 100 score",
                "normalized_score": cost_norm,
                "industrial_electricity_cents_kwh": cost_data.get("industrial_electricity_cents_kwh"),
                "coverage":         cost_data.get("coverage"),
                "note":             cost_data.get("note"),
            },
        },
    }
    if country == "China":
        d["proxies"]["energy_cost_access"]["dc_zone_electricity_cents_kwh"] = cost_data.get("dc_zone_electricity_cents_kwh")
    return d


def interpretive_sentence(us_score: float | None, cn_score: float | None) -> str:
    if us_score is None or cn_score is None:
        return "Insufficient data to compare AI energy scaling capacity at this time."
    diff = us_score - cn_score
    if abs(diff) < 4:
        return (
            "Energy capacity and constraints are broadly comparable — "
            "no clear advantage in AI energy scaling capacity on these proxies."
        )
    elif diff > 0:
        return (
            f"The U.S. shows stronger capacity to support AI energy demand "
            f"on these proxies (composite gap: {diff:+.1f} points). "
        )
    else:
        return (
            f"China shows stronger capacity to scale AI energy infrastructure "
            f"on these proxies (composite gap: {abs(diff):.1f} points, China ahead). "
            f"China\u2019s substantially faster electricity capacity expansion rate "
            f"and lower grid demand pressure give it more runway to expand AI compute. "
            f"U.S. grid interconnection backlogs and rising DC demand are material "
            f"constraints. Note: China\u2019s capacity additions are predominantly "
            f"variable renewable (solar/wind), which provides less firm 24/7 power "
            f"than the raw addition rate implies."
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now   = datetime.now(timezone.utc)
    us    = build_country_block("US")
    china = build_country_block("China")

    us_score    = us["composite_score"]
    china_score = china["composite_score"]

    output = {
        "schema_version":  "2.0",
        "dimension":       "energy",
        "metric_key":      "ai_energy_scaling_index",
        "title":           "Energy & Power Constraints \u2014 AI Scaling Capacity",
        "subtitle": (
            "Composite proxy for each country\u2019s ability to sustain large-scale "
            "AI compute growth \u2014 not a measure of total electricity generation."
        ),
        "description": (
            "A four-proxy composite index measuring AI energy scaling capacity: "
            "electricity capacity addition rate (30%), data center power demand "
            "headroom (25%), grid connection speed (25%), and energy cost & DC "
            "power access (20%). Higher score = greater ability to expand AI compute "
            "infrastructure without hitting energy supply, grid, or cost bottlenecks."
        ),
        "fetched_at":   now.isoformat(),
        "last_updated": now.isoformat(),
        "summary": {
            "US":    us,
            "China": china,
        },
        "ai_dc_pipeline_context": AI_DC_PIPELINE,
        "interpretive_sentence": interpretive_sentence(us_score, china_score),
        "composite_construction": {
            "method": (
                f"Weighted average of four normalized proxy scores. "
                f"Capacity addition rate: (rate / {CAPACITY_NORM_MAX}) \u00d7 100. "
                f"DC demand headroom: ({HEADROOM_NORM_REF} \u2212 dc_pct) / {HEADROOM_NORM_REF} \u00d7 100 "
                f"(inverted: lower demand share = more headroom = higher score). "
                f"Grid speed and energy cost are curated 0\u2013100 scores. "
                f"Weights: capacity {WEIGHT_CAPACITY:.0%}, headroom {WEIGHT_HEADROOM:.0%}, "
                f"grid {WEIGHT_GRID:.0%}, energy cost {WEIGHT_ENERGY_COST:.0%}."
            ),
            "weights": {
                "capacity_addition_rate": WEIGHT_CAPACITY,
                "dc_demand_headroom":     WEIGHT_HEADROOM,
                "grid_connection_speed":  WEIGHT_GRID,
                "energy_cost_access":     WEIGHT_ENERGY_COST,
            },
            "normalization": {
                "capacity_norm_max":  CAPACITY_NORM_MAX,
                "headroom_norm_ref":  HEADROOM_NORM_REF,
                "grid_speed_range":   "0\u2013100 (curated)",
                "energy_cost_range":  "0\u2013100 (curated)",
            },
        },
        "proxies_meta": {
            "capacity_addition_rate": CAPACITY_ADDITION_META,
            "dc_demand_headroom":     DC_DEMAND_META,
            "grid_connection_speed":  GRID_SPEED_META,
            "energy_cost_access":     ENERGY_COST_META,
        },
        "methodology_note": (
            "This index measures AI energy scaling capacity \u2014 the ability to add "
            "power supply, connect it to data centers quickly, and do so at cost-effective "
            "rates \u2014 not total electricity generation or consumption. "
            "Key distinction: a country with high generation capacity but severe "
            "interconnection constraints, high costs, or unreliable supply will score "
            "lower than raw capacity would suggest. "
            "Important caveat on capacity additions: the majority of new capacity in "
            "both countries is variable renewable (solar/wind). AI data centers require "
            "firm 24/7 power; renewables require storage or backup to serve this need. "
            "The capacity score thus slightly overstates near-term AI-usable expansion, "
            "particularly for China where >95% of 2024 additions were variable renewable."
        ),
        "coverage_note": (
            "Capacity addition rate: high confidence (EIA/IEA annual publications). "
            "DC demand headroom: high confidence for US; medium for China (less granular "
            "DC statistics). Grid connection speed: medium confidence for both \u2014 "
            "curated composite assessment. Energy cost & access: medium confidence for "
            "both \u2014 actual contracted rates for large operators are commercially "
            "sensitive and differ from published averages."
        ),
        "what_this_does_not_capture": [
            "Total electricity generation or consumption (not an AI-relevant measure on its own)",
            "Capacity factor / firmness of power — solar/wind additions provide fewer AI-usable MWh than the nameplate MW implies",
            "Carbon intensity or renewable mix of AI-relevant power (important for ESG and regulatory risk)",
            "Nuclear power expansion (US SMR pipeline; China's 23+ units under construction as of 2024)",
            "Private or off-grid power arrangements (natural gas generators co-located with AI campuses)",
            "Water availability constraints for data center cooling (increasingly binding in arid US SW)",
            "Long-run transmission adequacy (UHV buildout pace in China; US long-distance HVDC projects)",
            "Actual PPA prices for specific hyperscaler contracts (commercially sensitive)",
            "Regional grid reliability scores (NERC region data for US; provincial reliability in China)",
        ],
        "sources": [
            {
                "proxy": "capacity_addition_rate",
                "name":  "U.S. EIA, Electric Power Monthly (February 2025)",
                "url":   "https://www.eia.gov/electricity/monthly/",
                "edition": "2024 data",
            },
            {
                "proxy": "capacity_addition_rate",
                "name":  "IEA, Renewables 2024",
                "url":   "https://www.iea.org/reports/renewables-2024",
                "edition": "November 2024 (2024 data)",
            },
            {
                "proxy": "capacity_addition_rate",
                "name":  "China National Energy Administration (NEA) 2024 Annual Report / 国家能源局2024年能源工作综述",
                "url":   "https://www.nea.gov.cn/",
                "edition": "2024 data",
            },
            {
                "proxy": "dc_demand_headroom",
                "name":  "IEA, Energy and AI",
                "url":   "https://www.iea.org/reports/energy-and-ai",
                "edition": "January 2025",
            },
            {
                "proxy": "dc_demand_headroom",
                "name":  "IEA, Electricity 2025",
                "url":   "https://www.iea.org/reports/electricity-2025",
                "edition": "January 2025",
            },
            {
                "proxy": "grid_connection_speed",
                "name":  "LBNL, Queued Up: Characteristics of Power Plants Seeking Transmission Interconnection (2025 edition)",
                "url":   "https://emp.lbl.gov/queues",
                "edition": "2025",
            },
            {
                "proxy": "grid_connection_speed",
                "name":  "IEA, Energy and AI",
                "url":   "https://www.iea.org/reports/energy-and-ai",
                "edition": "January 2025",
            },
            {
                "proxy": "energy_cost_access",
                "name":  "U.S. EIA, Annual Energy Outlook 2025",
                "url":   "https://www.eia.gov/outlooks/aeo/",
                "edition": "2025",
            },
            {
                "proxy": "energy_cost_access",
                "name":  "China NBS Statistical Yearbook 2024 / 中国统计年鉴2024",
                "url":   "https://www.stats.gov.cn/sj/ndsj/",
                "edition": "2024",
            },
            {
                "proxy": "energy_cost_access",
                "name":  "China NDRC, East Data West Compute (东数西算) Policy Framework 2022–2024",
                "url":   "https://www.ndrc.gov.cn/",
                "edition": "2022–2024",
            },
        ],
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUTPUT_FILE}")
    print(f"  US composite:    {us_score}")
    print(f"  China composite: {china_score}")
    if us_score is not None and china_score is not None:
        gap    = abs(us_score - china_score)
        leader = "US" if us_score > china_score else "China"
        print(f"  Leader: {leader}  gap: {gap:.1f} points")


if __name__ == "__main__":
    main()
