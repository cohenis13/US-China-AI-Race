#!/usr/bin/env python3
"""
Fetch AI investment data from two sources and produce data/investment.json.

PRIMARY COMPOSITE SCORE DRIVERS
  1. Private AI Investment (70% weight)
     Hardcoded annual series from Stanford AI Index (economy chapter, PitchBook data).
     2024: US $109.1B vs China $9.3B — "nearly 12x" gap.
     Updated once/year when new AI Index report publishes (typically Feb–Apr).

  2. Hyperscaler AI/Data-Center Capex (30% weight)
     Annual capital expenditure from SEC EDGAR XBRL company-concept API (free, no auth).
     US: Microsoft, Alphabet, Amazon, Meta (10-K filers)
     China: Alibaba, Baidu (20-F filers — understates China; ByteDance/Tencent/Huawei excluded)
     Updated automatically whenever a new 10-K or 20-F is filed.

CONTEXT ONLY (not in composite score)
  3. US Government AI R&D  — NITRD annual budget supplement (hardcoded, update annually)
  4. China AI R&D estimate — CSET 2019 provisional findings (static, wide uncertainty range)

COMPOSITE FORMULA
  us_comp  = 0.70 * priv_us_share + 0.30 * capex_us_share
  cn_comp  = 100.0 − us_comp
  (each share = US / (US + China) × 100)

OUTPUT: data/investment.json

Usage:
    pip install requests
    python scripts/fetch_investment.py
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package required.  Run: pip install requests")
    sys.exit(1)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "investment.json"

# ── Weights ────────────────────────────────────────────────────────────────────
WEIGHTS = {"private_investment": 0.70, "hyperscaler_capex": 0.30}

# ══════════════════════════════════════════════════════════════════════════════
#  1. Stanford AI Index — Private AI Investment Series
# ══════════════════════════════════════════════════════════════════════════════
# Source: Stanford HAI AI Index annual reports (economy chapter, PitchBook data)
# 2024 figures explicitly stated: "U.S. private AI investment hit $109.1B,
# nearly 12× China's $9.3B" — Stanford AI Index 2025, Economy chapter.
# Earlier years from AI Index 2022–2024 reports; pre-2022 figures are estimates
# based on reported country shares and global totals.
#
# UPDATE PROCEDURE: When a new AI Index publishes, update the latest entry
# (or append a new row) with the verified country-level figures.

PRIVATE_AI_INVESTMENT = [
    # (year, us_usd_b, china_usd_b, source_report)
    (2017,   4.7,   1.8, "AI Index 2022 (estimated)"),
    (2018,   8.7,   3.8, "AI Index 2022 (estimated)"),
    (2019,  11.2,   5.2, "AI Index 2022 (estimated)"),
    (2020,  17.1,   9.7, "AI Index 2022"),
    (2021,  57.3,  17.2, "AI Index 2022"),
    (2022,  47.4,  13.4, "AI Index 2023"),
    (2023,  67.2,   7.6, "AI Index 2024"),
    (2024, 109.1,   9.3, "AI Index 2025"),
]

# ══════════════════════════════════════════════════════════════════════════════
#  2. NITRD — US Government AI R&D (context only)
# ══════════════════════════════════════════════════════════════════════════════
# Source: NSTC/NITRD Supplement to the President's Budget (AI PCA crosscut)
# FY2025: $3.316B total ($1.954B core AI + $1.361B crosscut support)
# https://www.nitrd.gov/budgetinformation/
#
# UPDATE PROCEDURE: When new Supplement publishes (spring), append a new row.

NITRD_US_AI_RD = [
    # (fiscal_year, total_ai_usd_b)
    (2020, 1.995),
    (2021, 2.204),
    (2022, 2.589),
    (2023, 2.913),
    (2024, 3.032),
    (2025, 3.316),
]

# China AI R&D — CSET 2019 provisional estimate (static; no reliable annual series)
CHINA_AI_RD_ESTIMATE_B  = 5.2          # midpoint, USD billions
CHINA_AI_RD_RANGE_B     = (1.6, 15.0)  # CSET uncertainty range
CHINA_AI_RD_SOURCE      = (
    "CSET 'Chinese Public AI R&D Spending: Provisional Findings' (2019). "
    "2018 base year estimate; wide uncertainty range reflects incomplete budget transparency."
)

# ══════════════════════════════════════════════════════════════════════════════
#  3. SEC EDGAR XBRL — Hyperscaler Capex
# ══════════════════════════════════════════════════════════════════════════════
# API: https://data.sec.gov/api/xbrl/companyconcept/CIK{10digit}/us-gaap/{concept}.json
# No auth required. Respect rate limit: ≤ 10 req/s.
# XBRL concept for capital expenditure (payments for PP&E):
#   PaymentsToAcquirePropertyPlantAndEquipment  (primary)
#   PurchasesOfPropertyAndEquipment             (fallback)

SEC_UA      = "us-china-ai-tracker research@github-actions.io"   # SEC requires email in UA
SEC_BASE    = "https://data.sec.gov/api/xbrl/companyconcept"
SEC_NS      = "us-gaap"
SEC_CAPEX_P = "PaymentsToAcquirePropertyPlantAndEquipment"
SEC_CAPEX_F = "PurchasesOfPropertyAndEquipment"
SEC_TIMEOUT = 30
SEC_DELAY   = 0.15   # seconds between requests

US_COMPANIES = [
    {"name": "Microsoft",  "cik": 789019,  "ticker": "MSFT"},
    {"name": "Alphabet",   "cik": 1652044, "ticker": "GOOGL"},
    {"name": "Amazon",     "cik": 1018724, "ticker": "AMZN"},
    {"name": "Meta",       "cik": 1326801, "ticker": "META"},
]

CHINA_COMPANIES = [
    # SEC 20-F filers only — ByteDance (private), Tencent (HKEX), Huawei (private) excluded
    {"name": "Alibaba",    "cik": 1577552, "ticker": "BABA"},
    {"name": "Baidu",      "cik": 1101239, "ticker": "BIDU"},
]

# Fallback capex values from most recent published annual reports.
# Used when SEC EDGAR API is unavailable (rate-limited, network error, etc.)
# UPDATE: Refresh when a new 10-K / 20-F is filed.
# Sources: SEC 10-K / 20-F filings (see period_end for fiscal year reference)
CAPEX_FALLBACK: dict[str, tuple[float, str]] = {
    # ticker: (capex_usd_b, period_end)
    "MSFT":  (44.5,  "2024-06-30"),  # Microsoft FY2024 10-K
    "GOOGL": (52.5,  "2024-12-31"),  # Alphabet FY2024 10-K
    "AMZN":  (77.7,  "2024-12-31"),  # Amazon FY2024 10-K
    "META":  (37.7,  "2024-12-31"),  # Meta FY2024 10-K
    "BABA":  (11.9,  "2025-03-31"),  # Alibaba FY2025 20-F (fiscal yr ends Mar 31)
    "BIDU":  (2.0,   "2024-12-31"),  # Baidu FY2024 20-F
}


def _fetch_concept(cik: int, concept: str) -> list[dict]:
    """Fetch all USD entries for one XBRL concept from SEC EDGAR. Returns [] on error."""
    cik_str = str(cik).zfill(10)
    url     = f"{SEC_BASE}/CIK{cik_str}/{SEC_NS}/{concept}.json"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": SEC_UA, "Accept": "application/json"},
            timeout=SEC_TIMEOUT,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("units", {}).get("USD", [])
    except requests.exceptions.RequestException as e:
        log.warning("SEC EDGAR fetch failed (CIK %d / %s): %s", cik, concept, e)
        return []


def get_annual_capex(cik: int) -> tuple[float | None, str]:
    """
    Return (capex_usd_b, period_end_date) for the most recent annual filing
    (10-K for US companies, 20-F for foreign private issuers).
    Tries primary concept, then fallback concept.
    """
    for concept in (SEC_CAPEX_P, SEC_CAPEX_F):
        entries = _fetch_concept(cik, concept)
        time.sleep(SEC_DELAY)
        if not entries:
            continue

        # Annual entries: fp == "FY" in 10-K / 20-F filings
        annual = [
            e for e in entries
            if e.get("form") in ("10-K", "20-F")
            and e.get("fp") == "FY"
            and e.get("val") and e["val"] > 0
        ]
        # Fallback: any entry in an annual filing (some foreign filers don't tag fp="FY")
        if not annual:
            annual = [
                e for e in entries
                if e.get("form") in ("10-K", "20-F")
                and e.get("val") and e["val"] > 0
            ]

        if annual:
            annual.sort(key=lambda x: x.get("end", ""), reverse=True)
            latest = annual[0]
            return round(latest["val"] / 1e9, 2), latest.get("end", "")

    return None, ""


def fetch_hyperscaler_capex(companies: list[dict]) -> list[dict]:
    """Fetch annual capex for a list of companies, with fallback to known values."""
    results = []
    for c in companies:
        ticker = c["ticker"]
        log.info("  %s (CIK %d) …", c["name"], c["cik"])
        capex, period_end = get_annual_capex(c["cik"])

        source = "SEC EDGAR XBRL"
        if capex is not None:
            log.info("    → $%.1fB  (period end %s)", capex, period_end)
        else:
            # Fall back to known published values
            fallback = CAPEX_FALLBACK.get(ticker)
            if fallback:
                capex, period_end = fallback
                source = "fallback (published annual report)"
                log.info("    → $%.1fB fallback (period end %s)", capex, period_end)
            else:
                log.warning("    → capex not found and no fallback available")

        results.append({
            "name":        c["name"],
            "ticker":      ticker,
            "capex_usd_b": capex,
            "period_end":  period_end,
            "data_source": source,
        })
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:

    # ── Private AI Investment ─────────────────────────────────────────────────
    yr, us_priv, cn_priv, src = PRIVATE_AI_INVESTMENT[-1]
    priv_total    = us_priv + cn_priv
    us_priv_share = round(us_priv / priv_total * 100, 1) if priv_total else 50.0
    cn_priv_share = round(100.0 - us_priv_share, 1)

    log.info("Private AI investment (%d, %s): US $%.1fB  China $%.1fB  US_share=%.1f%%",
             yr, src, us_priv, cn_priv, us_priv_share)

    series = [
        {
            "year":        y,
            "us_usd_b":    u,
            "china_usd_b": c,
            "us_share":    round(u / (u + c) * 100, 1) if (u + c) else None,
            "source":      s,
        }
        for y, u, c, s in PRIVATE_AI_INVESTMENT
    ]

    # ── Hyperscaler Capex ─────────────────────────────────────────────────────
    log.info("Fetching hyperscaler capex from SEC EDGAR …")
    us_firms   = fetch_hyperscaler_capex(US_COMPANIES)
    cn_firms   = fetch_hyperscaler_capex(CHINA_COMPANIES)

    us_capex = sum(f["capex_usd_b"] for f in us_firms if f["capex_usd_b"] is not None)
    cn_capex = sum(f["capex_usd_b"] for f in cn_firms if f["capex_usd_b"] is not None)
    capex_total    = us_capex + cn_capex
    us_capex_share = round(us_capex / capex_total * 100, 1) if capex_total else 50.0
    cn_capex_share = round(100.0 - us_capex_share, 1)

    log.info("Hyperscaler capex: US $%.1fB  China $%.1fB  US_share=%.1f%%",
             us_capex, cn_capex, us_capex_share)

    # ── Composite Score ───────────────────────────────────────────────────────
    us_comp = round(
        WEIGHTS["private_investment"] * us_priv_share
        + WEIGHTS["hyperscaler_capex"]  * us_capex_share,
        1,
    )
    cn_comp = round(100.0 - us_comp, 1)

    log.info("Composite: US=%.1f  China=%.1f", us_comp, cn_comp)

    # ── NITRD context ─────────────────────────────────────────────────────────
    nitrd_fy, nitrd_b = NITRD_US_AI_RD[-1]

    # ── Build output ──────────────────────────────────────────────────────────
    output = {
        "dimension":   "investment",
        "metric_key":  "ai_investment_composite",
        "description": (
            "AI investment composite: private AI VC/startup investment (70%, Stanford AI Index "
            "annual series, PitchBook data) + hyperscaler AI/data-center capex (30%, SEC EDGAR "
            "annual 10-K/20-F filings). Government AI R&D (NITRD + CSET) shown as context only."
        ),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "US": {
                "composite_score":          us_comp,
                "private_investment_usd_b": us_priv,
                "hyperscaler_capex_usd_b":  round(us_capex, 1),
            },
            "China": {
                "composite_score":          cn_comp,
                "private_investment_usd_b": cn_priv,
                "hyperscaler_capex_usd_b":  round(cn_capex, 1),
            },
        },
        "weights": WEIGHTS,

        # ── Sub-metric 1: Private AI Investment ──────────────────────────────
        "private_investment": {
            "source":         "Stanford AI Index annual reports (PitchBook data)",
            "source_url":     "https://hai.stanford.edu/ai-index/2025-ai-index-report/economy",
            "update_cadence": "Annual — update when new AI Index report publishes (Feb–Apr)",
            "latest_year":    yr,
            "us_usd_b":       us_priv,
            "china_usd_b":    cn_priv,
            "us_share":       us_priv_share,
            "china_share":    cn_priv_share,
            "series":         series,
        },

        # ── Sub-metric 2: Hyperscaler Capex ──────────────────────────────────
        "hyperscaler_capex": {
            "source":     "SEC EDGAR XBRL company-concept API",
            "source_url": "https://data.sec.gov",
            "concept":    SEC_CAPEX_P,
            "note": (
                "Annual capex (most recent 10-K for US firms; 20-F for China SEC filers). "
                "China side covers only Alibaba and Baidu — ByteDance (private), "
                "Tencent (HKEX only), and Huawei (private) are excluded. "
                "China hyperscaler capex is materially understated."
            ),
            "us_total_usd_b":    round(us_capex, 1),
            "china_total_usd_b": round(cn_capex, 1),
            "us_share":          us_capex_share,
            "us_firms":          us_firms,
            "china_firms":       cn_firms,
        },

        # ── Context: Government AI R&D ────────────────────────────────────────
        "gov_rd": {
            "note": (
                "Shown as context only — excluded from composite score. "
                "US NITRD figures are directly measured; China R&D is an estimate "
                "with ~10× uncertainty range. Not bilaterally comparable."
            ),
            "us": {
                "source":         "NITRD Supplement to the President's Budget (NSTC AI PCA)",
                "source_url":     "https://www.nitrd.gov/budgetinformation/",
                "latest_fy":      nitrd_fy,
                "total_ai_usd_b": nitrd_b,
                "series": [{"fy": f, "total_ai_usd_b": b} for f, b in NITRD_US_AI_RD],
            },
            "china": {
                "source":           CHINA_AI_RD_SOURCE,
                "estimate_usd_b":   CHINA_AI_RD_ESTIMATE_B,
                "range_usd_b":      list(CHINA_AI_RD_RANGE_B),
                "base_year":        2018,
            },
        },

        "methodology_note": (
            f"Composite = {int(WEIGHTS['private_investment']*100)}% private AI investment share + "
            f"{int(WEIGHTS['hyperscaler_capex']*100)}% hyperscaler capex share (each = US/(US+China)×100). "
            "Private investment is the dominant signal (Stanford AI Index, well-cited, updated annually). "
            "Capex comparison systematically understates China — Tencent, ByteDance, and Huawei are "
            "absent from SEC EDGAR. Both metrics favor the US strongly; this reflects genuine "
            "private-sector investment asymmetry, not a measurement artefact. "
            "Government R&D spending is excluded from the composite — China likely matches or exceeds "
            "the US on public AI R&D, but the measurement uncertainty is too large for bilateral scoring."
        ),
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    log.info("")
    log.info("Output: %s", OUTPUT_FILE)
    log.info("Composite:            US=%.1f%%  China=%.1f%%", us_comp, cn_comp)
    log.info("  Private investment: US $%.1fB  China $%.1fB  (US_share=%.1f%%)",
             us_priv, cn_priv, us_priv_share)
    log.info("  Hyperscaler capex:  US $%.1fB  China $%.1fB  (US_share=%.1f%%)",
             us_capex, cn_capex, us_capex_share)
    log.info("  Gov AI R&D (ctx):   US FY%d $%.1fB | China ~$%.1fB (CSET est.)",
             nitrd_fy, nitrd_b, CHINA_AI_RD_ESTIMATE_B)


if __name__ == "__main__":
    main()
