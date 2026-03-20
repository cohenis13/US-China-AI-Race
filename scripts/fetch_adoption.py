#!/usr/bin/env python3
"""
AI Adoption proxy — public company filing disclosure rate.

WHAT THIS MEASURES
  The share of major listed companies whose latest annual filing (10-K for US,
  20-F for Chinese ADRs) contains evidence of AI deployment, integration, or
  operational AI use. Used as a country-level proxy for economy-wide AI adoption
  among large firms.

METHODOLOGY
  Sample: Curated list of ~25 US companies (S&P 500, diverse sectors) and
          ~20 major Chinese companies that file 20-F on SEC EDGAR (Chinese ADRs).
  Source: SEC EDGAR full-text search (EFTS) at efts.sec.gov.
  Window: Rolling 30-month filing window — captures the latest annual filing
          for each company regardless of fiscal year end.
  Classification (per company):
    "deployment" — annual filing mentions "generative AI" or "large language
                   model" → strong evidence of operational AI engagement.
    "strategic"  — filing mentions "artificial intelligence" but not the above
                   terms → AI strategy/planning language, no strong deployment
                   signal.
    "unknown"    — company's filing not found or API inaccessible.
  Adoption rate = deployment / (deployment + strategic) × 100.
  "Unknown" companies are excluded from the rate.

COVERAGE NOTES
  China sample covers only US-listed Chinese ADRs (Alibaba, Baidu, JD, PDD…).
  Major Chinese companies that do not file with the SEC (Tencent, ByteDance,
  CATL, ICBC, etc.) are NOT covered. This is acknowledged, not hidden.
  US sample covers major S&P 500 companies across Technology, Finance,
  Healthcare, Retail, Industrial, and Energy sectors.

Outputs to data/adoption.json.
"""

import json
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
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
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "adoption.json"

# ── Config ────────────────────────────────────────────────────────────────────
WINDOW_MONTHS   = 30      # filing window (months back from today)
SLEEP_SECS      = 1.2     # pause between EDGAR EFTS requests
RETRY_COUNT     = 3       # retries on 429 / 403
RETRY_BACKOFF   = [3, 6, 12]  # seconds between retries

EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_HEADERS  = {
    "User-Agent": (
        "us-china-ai-tracker (non-commercial public research; "
        "github.com/cohenis13/US-China-AI-Race)"
    ),
    "Accept": "application/json",
}

# ── Deployment detection terms ─────────────────────────────────────────────────
# Strong signal: specific to the post-2022 AI wave; presence in an annual filing
# is a reliable indicator of meaningful AI engagement.
STRONG_TERMS = ['"generative AI"', '"large language model"']

# Weak signal: general AI language present in virtually every major company
# 10-K since ~2017. Used only to verify the company's filing was found.
WEAK_TERM = '"artificial intelligence"'

# ── Curated company sample ────────────────────────────────────────────────────
# entity: the name as it appears in EDGAR (case-insensitive substring match).
# form:   10-K for US domestic, 20-F for foreign private issuers.

US_FIRMS = [
    {"name": "Microsoft",            "entity": "microsoft corp",                  "form": "10-K", "sector": "Technology"},
    {"name": "Apple",                "entity": "apple inc",                       "form": "10-K", "sector": "Technology"},
    {"name": "Alphabet",             "entity": "alphabet inc",                    "form": "10-K", "sector": "Technology"},
    {"name": "Amazon",               "entity": "amazon com inc",                  "form": "10-K", "sector": "Technology"},
    {"name": "Meta Platforms",       "entity": "meta platforms inc",              "form": "10-K", "sector": "Technology"},
    {"name": "Nvidia",               "entity": "nvidia corp",                     "form": "10-K", "sector": "Technology"},
    {"name": "Salesforce",           "entity": "salesforce inc",                  "form": "10-K", "sector": "Technology"},
    {"name": "Adobe",                "entity": "adobe inc",                       "form": "10-K", "sector": "Technology"},
    {"name": "IBM",                  "entity": "international business machines", "form": "10-K", "sector": "Technology"},
    {"name": "ServiceNow",           "entity": "servicenow inc",                  "form": "10-K", "sector": "Technology"},
    {"name": "JPMorgan Chase",       "entity": "jpmorgan chase",                  "form": "10-K", "sector": "Finance"},
    {"name": "Goldman Sachs",        "entity": "goldman sachs group",             "form": "10-K", "sector": "Finance"},
    {"name": "Bank of America",      "entity": "bank of america corp",            "form": "10-K", "sector": "Finance"},
    {"name": "Citigroup",            "entity": "citigroup inc",                   "form": "10-K", "sector": "Finance"},
    {"name": "UnitedHealth Group",   "entity": "unitedhealth group",              "form": "10-K", "sector": "Healthcare"},
    {"name": "Johnson & Johnson",    "entity": "johnson johnson",                 "form": "10-K", "sector": "Healthcare"},
    {"name": "Walmart",              "entity": "walmart inc",                     "form": "10-K", "sector": "Retail"},
    {"name": "Home Depot",           "entity": "home depot inc",                  "form": "10-K", "sector": "Retail"},
    {"name": "Procter & Gamble",     "entity": "procter gamble co",               "form": "10-K", "sector": "Consumer"},
    {"name": "Honeywell",            "entity": "honeywell international",         "form": "10-K", "sector": "Industrial"},
    {"name": "Boeing",               "entity": "boeing co",                       "form": "10-K", "sector": "Industrial"},
    {"name": "AT&T",                 "entity": "at t inc",                        "form": "10-K", "sector": "Telecom"},
    {"name": "Verizon",              "entity": "verizon communications",          "form": "10-K", "sector": "Telecom"},
    {"name": "ExxonMobil",           "entity": "exxon mobil corp",               "form": "10-K", "sector": "Energy"},
    {"name": "Walt Disney",          "entity": "walt disney co",                  "form": "10-K", "sector": "Media"},
]

# Chinese companies that file 20-F with the SEC — primarily large tech,
# e-commerce, and auto companies. Does NOT include Tencent, ByteDance,
# Huawei, or state-owned enterprises that do not file with the SEC.
CN_FIRMS = [
    {"name": "Alibaba",             "entity": "alibaba group",          "form": "20-F", "sector": "Technology"},
    {"name": "Baidu",               "entity": "baidu inc",              "form": "20-F", "sector": "Technology"},
    {"name": "JD.com",              "entity": "jd com inc",             "form": "20-F", "sector": "Technology"},
    {"name": "PDD Holdings",        "entity": "pdd holdings",           "form": "20-F", "sector": "Technology"},
    {"name": "NetEase",             "entity": "netease inc",            "form": "20-F", "sector": "Technology"},
    {"name": "Trip.com",            "entity": "trip com group",         "form": "20-F", "sector": "Technology"},
    {"name": "Bilibili",            "entity": "bilibili inc",           "form": "20-F", "sector": "Technology"},
    {"name": "iQIYI",               "entity": "iqiyi inc",              "form": "20-F", "sector": "Technology"},
    {"name": "NIO",                 "entity": "nio inc",                "form": "20-F", "sector": "Automotive"},
    {"name": "Xpeng",               "entity": "xpeng inc",              "form": "20-F", "sector": "Automotive"},
    {"name": "Li Auto",             "entity": "li auto inc",            "form": "20-F", "sector": "Automotive"},
    {"name": "ZTO Express",         "entity": "zto express",            "form": "20-F", "sector": "Logistics"},
    {"name": "Vipshop",             "entity": "vipshop holdings",       "form": "20-F", "sector": "Retail"},
    {"name": "New Oriental",        "entity": "new oriental education", "form": "20-F", "sector": "Education"},
    {"name": "Yum China",           "entity": "yum china holdings",     "form": "20-F", "sector": "Consumer"},
    {"name": "Kanzhun",             "entity": "kanzhun limited",        "form": "20-F", "sector": "Technology"},
    {"name": "Full Truck Alliance", "entity": "full truck alliance",    "form": "20-F", "sector": "Logistics"},
    {"name": "JOYY",                "entity": "joyy inc",               "form": "20-F", "sector": "Technology"},
    {"name": "Lufax",               "entity": "lufax holding",          "form": "20-F", "sector": "Finance"},
    {"name": "Agora",               "entity": "agora inc",              "form": "20-F", "sector": "Technology"},
]


# ── EDGAR EFTS helpers ────────────────────────────────────────────────────────
def _efts_request(session: requests.Session, params: dict, label: str) -> dict | None:
    """
    Single EDGAR EFTS GET request with retry on 429/403.
    Returns parsed JSON dict or None on failure.
    """
    time.sleep(SLEEP_SECS)
    for attempt in range(RETRY_COUNT):
        try:
            resp = session.get(
                EDGAR_EFTS_URL,
                params=params,
                headers=EDGAR_HEADERS,
                timeout=20,
            )
            if resp.status_code in (429, 403):
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                log.warning("%s: HTTP %d — waiting %ds before retry %d/%d",
                            label, resp.status_code, wait, attempt + 1, RETRY_COUNT)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            log.error("%s: HTTP error %s", label, e)
            return None
        except Exception as e:
            log.error("%s: request failed — %s", label, e)
            return None
    log.error("%s: all retries exhausted", label)
    return None


def _hit_count(data: dict | None) -> int:
    """Extract total hit count from EFTS response, 0 on any problem."""
    if data is None:
        return -1  # distinguish "failed" from "found 0"
    total = data.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        return int(total.get("value", 0))
    if isinstance(total, int):
        return total
    return 0


# ── Per-company classification ────────────────────────────────────────────────
def classify_firm(firm: dict, start_date: str, end_date: str,
                  session: requests.Session) -> dict:
    """
    Classify one firm's AI adoption status using EDGAR EFTS.

    Returns a dict with:
      name, country, sector, form, classification, matched_term
    """
    base_params = {
        "forms":     firm["form"],
        "dateRange": "custom",
        "startdt":   start_date,
        "enddt":     end_date,
        "entity":    firm["entity"],
    }

    # ── Step 1: strong deployment terms ─────────────────────────────────────
    for term in STRONG_TERMS:
        params = {**base_params, "q": term}
        data   = _efts_request(session, params, f"{firm['name']} / {term}")
        count  = _hit_count(data)
        if count < 0:
            # API failure — mark unknown, stop checking this firm
            log.warning("  %s → unknown (API failure on strong term)", firm["name"])
            return _firm_result(firm, "unknown", "api_failure")
        if count > 0:
            log.info("  %s → deployment (%s, %d filing(s))", firm["name"], term.strip('"'), count)
            return _firm_result(firm, "deployment", term.strip('"'))

    # ── Step 2: fallback — confirm filing exists via general AI term ─────────
    params = {**base_params, "q": WEAK_TERM}
    data   = _efts_request(session, params, f"{firm['name']} / AI mention")
    count  = _hit_count(data)
    if count < 0:
        log.warning("  %s → unknown (API failure on weak term)", firm["name"])
        return _firm_result(firm, "unknown", "api_failure")
    if count > 0:
        log.info("  %s → strategic (AI mentioned, no deployment terms; %d filing(s))", firm["name"], count)
        return _firm_result(firm, "strategic", "artificial intelligence")

    # 0 hits on both — entity likely not matched or no recent filing
    log.info("  %s → unknown (0 hits — entity may not match or no recent filing)", firm["name"])
    return _firm_result(firm, "unknown", "no_filings_found")


def _firm_result(firm: dict, classification: str, matched_term: str) -> dict:
    return {
        "name":           firm["name"],
        "entity":         firm["entity"],
        "country":        firm.get("country", ""),
        "sector":         firm.get("sector", ""),
        "form":           firm["form"],
        "classification": classification,
        "matched_term":   matched_term,
    }


# ── Aggregation ───────────────────────────────────────────────────────────────
def aggregate(results: list[dict]) -> dict:
    """
    Compute adoption rate from firm results.
    Unknown firms are excluded from the rate denominator.
    """
    deployment = sum(1 for r in results if r["classification"] == "deployment")
    strategic  = sum(1 for r in results if r["classification"] == "strategic")
    unknown    = sum(1 for r in results if r["classification"] == "unknown")
    denominator = deployment + strategic  # known firms only

    rate = round(deployment / denominator * 100, 1) if denominator > 0 else None
    return {
        "sample_size":       len(results),
        "adoption_positive": deployment,
        "strategic_only":    strategic,
        "unknown":           unknown,
        "adoption_rate":     rate,    # % of known firms with deployment signal
        "denominator":       denominator,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now      = datetime.now(timezone.utc)
    end_dt   = now.date()
    start_dt = (now - timedelta(days=30 * WINDOW_MONTHS)).date()
    start_date = str(start_dt)
    end_date   = str(end_dt)

    log.info("Filing window: %s → %s", start_date, end_date)
    log.info("US firms: %d  |  China firms: %d", len(US_FIRMS), len(CN_FIRMS))

    # Tag firms with country before processing
    for f in US_FIRMS:
        f["country"] = "US"
    for f in CN_FIRMS:
        f["country"] = "China"

    session = requests.Session()

    log.info("── US firms (10-K) ──────────────────────────────────────────")
    us_results = []
    for firm in US_FIRMS:
        result = classify_firm(firm, start_date, end_date, session)
        us_results.append(result)

    log.info("── China firms (20-F) ───────────────────────────────────────")
    cn_results = []
    for firm in CN_FIRMS:
        result = classify_firm(firm, start_date, end_date, session)
        cn_results.append(result)

    session.close()

    us_agg = aggregate(us_results)
    cn_agg = aggregate(cn_results)

    log.info("")
    log.info("US:    %d/%d deployment  (%s%% rate, %d unknown)",
             us_agg["adoption_positive"], us_agg["sample_size"],
             us_agg["adoption_rate"], us_agg["unknown"])
    log.info("China: %d/%d deployment  (%s%% rate, %d unknown)",
             cn_agg["adoption_positive"], cn_agg["sample_size"],
             cn_agg["adoption_rate"], cn_agg["unknown"])

    # Sanity: if EDGAR is fully blocked, both will have mostly unknowns
    us_known = us_agg["denominator"]
    cn_known = cn_agg["denominator"]
    if us_known < 5 and cn_known < 5:
        log.error("FAIL: too few known firms (US=%d, China=%d) — EDGAR may be blocked", us_known, cn_known)
        sys.exit(1)

    output = {
        "dimension":  "adoption",
        "metric_key": "filing_adoption_rate",
        "description": (
            "AI adoption proxy: share of major listed companies whose latest annual "
            "filing (10-K or 20-F) shows evidence of AI deployment or operational AI "
            "use. Based on SEC EDGAR full-text search for deployment-specific AI language."
        ),
        "fetched_at":        now.isoformat(),
        "last_updated":      now.isoformat(),
        "filing_window":     {"start": start_date, "end": end_date, "months": WINDOW_MONTHS},
        "classification": {
            "deployment": 'Filing mentions "generative AI" or "large language model" — strong operational AI signal.',
            "strategic":  'Filing mentions "artificial intelligence" but not above terms — strategy/planning language.',
            "unknown":    "Filing not found or EDGAR API inaccessible — excluded from rate.",
        },
        "summary": {
            "US":    us_agg,
            "China": cn_agg,
        },
        "firms": us_results + cn_results,
        "source": {
            "name":    "SEC EDGAR Full-Text Search (EFTS)",
            "url":     "https://efts.sec.gov/LATEST/search-index",
            "us_form": "10-K (annual report, US domestic companies)",
            "cn_form": "20-F (annual report, foreign private issuers — Chinese ADRs)",
        },
        "methodology_note": (
            "Adoption rate = companies with deployment signal / known-sample companies × 100. "
            '"Deployment signal" = filing mentions "generative AI" or "large language model". '
            '"Strategic only" = filing mentions "artificial intelligence" but not above terms. '
            "Company not found in EDGAR for the window = excluded from rate. "
            "US sample: ~25 major S&P 500 companies across diverse sectors. "
            "China sample: ~20 major Chinese ADRs filing 20-F with the SEC. "
            "Does NOT include Tencent, ByteDance, CATL, ICBC or other non-SEC filers. "
            "Compare directionally — absolute rates reflect the curated sample, not all firms."
        ),
        "caveats": (
            "1. China sample = US-listed ADRs only (tech-heavy). "
            "2. Deployment terms may appear in risk disclosures alongside confirmed use. "
            "3. Entity name matching may miss some filings; unknowns are excluded from rate. "
            "4. 30-month window captures latest annual filing regardless of fiscal year end."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Wrote %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
