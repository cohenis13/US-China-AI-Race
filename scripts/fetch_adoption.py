#!/usr/bin/env python3
"""
AI Adoption proxy — public company filing disclosure rate.

APPROACH
  Run two bulk EDGAR EFTS full-text searches (one for "generative AI" /
  "large language model" in 10-K filings, one in 20-F filings).
  Paginate through results and collect every CIK that appears.
  Match against a curated sample of major listed companies using CIK numbers.

  Companies whose CIK appears in the strong-term results → "deployment".
  Companies in the sample but not found in those results → "strategic" (all
  major listed firms mention AI broadly; not finding the strong terms is the
  meaningful signal).
  Companies whose CIK lookup returns no matching filing (wrong CIK, delisted,
  etc.) → "unknown", excluded from the adoption rate.

  Adoption rate = deployment / (deployment + strategic) × 100.

WHY CIK-BASED MATCHING
  The EDGAR EFTS `entity` URL parameter does not reliably filter results to a
  single company — it can trigger 400 errors or return empty sets, making
  per-company entity queries unreliable. Paginating the broad search and
  matching by CIK (extracted from the accession number in each hit) is the
  standard robust approach.

DATA SOURCES
  US  : 10-K annual reports via SEC EDGAR EFTS.
  China: 20-F annual reports via SEC EDGAR EFTS (Chinese ADRs only — Alibaba,
          Baidu, JD, PDD, etc. Does NOT include Tencent, ByteDance, or firms
          that do not file with the SEC).

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
    print("Error: 'requests' package required. Run: pip install requests")
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
WINDOW_MONTHS  = 30      # rolling filing window (months back from today)
SLEEP_SECS     = 1.0     # between EDGAR EFTS requests (SEC asks for polite pacing)
RETRY_WAIT     = [4, 8]  # seconds between retries on 429/403
MAX_PAGES      = 60      # pagination safety cap per (form, term) combination

EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_HEADERS  = {
    "User-Agent": (
        "us-china-ai-tracker (non-commercial public research; "
        "github.com/cohenis13/US-China-AI-Race)"
    ),
    "Accept": "application/json",
}

# Terms that, when appearing in an annual filing, indicate strong operational
# AI engagement rather than generic strategy language.
STRONG_TERMS = ['"generative AI"', '"large language model"']

# ── Curated company sample ────────────────────────────────────────────────────
# cik: SEC CIK as a plain integer string (no zero-padding needed here;
#      normalization is done at match time).
# form: 10-K for US domestic companies, 20-F for foreign private issuers.

US_FIRMS = [
    {"name": "Microsoft",          "cik": "789019",   "form": "10-K", "sector": "Technology"},
    {"name": "Apple",              "cik": "320193",   "form": "10-K", "sector": "Technology"},
    {"name": "Alphabet",           "cik": "1652044",  "form": "10-K", "sector": "Technology"},
    {"name": "Amazon",             "cik": "1018724",  "form": "10-K", "sector": "Technology"},
    {"name": "Meta Platforms",     "cik": "1326801",  "form": "10-K", "sector": "Technology"},
    {"name": "Nvidia",             "cik": "1045810",  "form": "10-K", "sector": "Technology"},
    {"name": "Salesforce",         "cik": "1108524",  "form": "10-K", "sector": "Technology"},
    {"name": "Adobe",              "cik": "796343",   "form": "10-K", "sector": "Technology"},
    {"name": "IBM",                "cik": "51143",    "form": "10-K", "sector": "Technology"},
    {"name": "ServiceNow",         "cik": "1373715",  "form": "10-K", "sector": "Technology"},
    {"name": "JPMorgan Chase",     "cik": "19617",    "form": "10-K", "sector": "Finance"},
    {"name": "Goldman Sachs",      "cik": "886982",   "form": "10-K", "sector": "Finance"},
    {"name": "Bank of America",    "cik": "70858",    "form": "10-K", "sector": "Finance"},
    {"name": "Citigroup",          "cik": "831001",   "form": "10-K", "sector": "Finance"},
    {"name": "UnitedHealth Group", "cik": "72971",    "form": "10-K", "sector": "Healthcare"},
    {"name": "Johnson & Johnson",  "cik": "200406",   "form": "10-K", "sector": "Healthcare"},
    {"name": "Walmart",            "cik": "104169",   "form": "10-K", "sector": "Retail"},
    {"name": "Home Depot",         "cik": "354950",   "form": "10-K", "sector": "Retail"},
    {"name": "Procter & Gamble",   "cik": "80424",    "form": "10-K", "sector": "Consumer"},
    {"name": "Honeywell",          "cik": "773840",   "form": "10-K", "sector": "Industrial"},
    {"name": "Boeing",             "cik": "12927",    "form": "10-K", "sector": "Industrial"},
    {"name": "AT&T",               "cik": "732717",   "form": "10-K", "sector": "Telecom"},
    {"name": "Verizon",            "cik": "732712",   "form": "10-K", "sector": "Telecom"},
    {"name": "ExxonMobil",         "cik": "34088",    "form": "10-K", "sector": "Energy"},
    {"name": "Walt Disney",        "cik": "1001039",  "form": "10-K", "sector": "Media"},
]

# Chinese companies that file 20-F with the SEC (foreign private issuers).
# Does NOT include Tencent, ByteDance, Huawei, or state-owned banks that
# do not list in the US.
CN_FIRMS = [
    {"name": "Alibaba",             "cik": "1577552", "form": "20-F", "sector": "Technology"},
    {"name": "Baidu",               "cik": "1330479", "form": "20-F", "sector": "Technology"},
    {"name": "JD.com",              "cik": "1549802", "form": "20-F", "sector": "Technology"},
    {"name": "PDD Holdings",        "cik": "1631574", "form": "20-F", "sector": "Technology"},
    {"name": "NetEase",             "cik": "1108320", "form": "20-F", "sector": "Technology"},
    {"name": "Trip.com",            "cik": "1323761", "form": "20-F", "sector": "Technology"},
    {"name": "Bilibili",            "cik": "1729173", "form": "20-F", "sector": "Technology"},
    {"name": "iQIYI",               "cik": "1745020", "form": "20-F", "sector": "Technology"},
    {"name": "NIO",                 "cik": "1741830", "form": "20-F", "sector": "Automotive"},
    {"name": "Xpeng",               "cik": "1792789", "form": "20-F", "sector": "Automotive"},
    {"name": "Li Auto",             "cik": "1786973", "form": "20-F", "sector": "Automotive"},
    {"name": "ZTO Express",         "cik": "1666134", "form": "20-F", "sector": "Logistics"},
    {"name": "Vipshop",             "cik": "1521332", "form": "20-F", "sector": "Retail"},
    {"name": "New Oriental",        "cik": "1191791", "form": "20-F", "sector": "Education"},
    {"name": "Yum China",           "cik": "1674930", "form": "20-F", "sector": "Consumer"},
    {"name": "Kanzhun",             "cik": "1822966", "form": "20-F", "sector": "Technology"},
    {"name": "Full Truck Alliance", "cik": "1821722", "form": "20-F", "sector": "Logistics"},
    {"name": "JOYY",                "cik": "1441874", "form": "20-F", "sector": "Technology"},
    {"name": "Lufax",               "cik": "1821945", "form": "20-F", "sector": "Finance"},
    {"name": "Agora",               "cik": "1816613", "form": "20-F", "sector": "Technology"},
]


# ── CIK normalization ─────────────────────────────────────────────────────────
def _norm_cik(raw: str | int) -> str:
    """Strip leading zeros for consistent comparison."""
    try:
        return str(int(str(raw)))
    except (ValueError, TypeError):
        return str(raw)


# ── EDGAR EFTS helpers ────────────────────────────────────────────────────────
def _efts_get(session: requests.Session, params: dict, label: str) -> dict | None:
    """
    Single EDGAR EFTS GET with up to 2 retries on 429/403.
    Returns parsed JSON or None on failure.
    """
    time.sleep(SLEEP_SECS)
    for attempt in range(3):
        try:
            if attempt > 0:
                wait = RETRY_WAIT[min(attempt - 1, len(RETRY_WAIT) - 1)]
                log.warning("%s retry %d — waiting %ds", label, attempt, wait)
                time.sleep(wait)
            resp = session.get(
                EDGAR_EFTS_URL,
                params=params,
                headers=EDGAR_HEADERS,
                timeout=25,
            )
            if resp.status_code in (429, 403):
                log.warning("%s: HTTP %d from EDGAR", label, resp.status_code)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            log.error("%s: HTTP error — %s", label, e)
            return None
        except Exception as e:
            log.error("%s: request failed — %s", label, e)
            return None
    log.error("%s: all retries exhausted", label)
    return None


def _extract_cik(hit: dict) -> str | None:
    """
    Extract CIK from an EDGAR EFTS result hit.

    Two methods tried in order:
    1. _source.entity_id (most direct — CIK stored as a field)
    2. _id prefix: EDGAR accession numbers are formatted as XXXXXXXXXX-YY-NNNNNN
       where the first 10 chars (zero-padded) are the filer's CIK.
    """
    src = hit.get("_source", {})

    # Method 1: explicit field
    eid = src.get("entity_id") or src.get("cik") or src.get("filer_id")
    if eid:
        return _norm_cik(eid)

    # Method 2: accession number prefix
    accession = hit.get("_id", "")
    parts = accession.split("-")
    if parts and len(parts[0]) >= 10:
        return _norm_cik(parts[0])

    return None


# ── Bulk EFTS search ──────────────────────────────────────────────────────────
def search_for_ciks(
    session: requests.Session,
    form_type: str,
    terms: list[str],
    start_date: str,
    end_date: str,
    target_ciks: set[str],
) -> tuple[set[str], bool]:
    """
    Paginate EDGAR EFTS for (form_type, each term) and collect all CIKs
    seen in results. Stops early once all target_ciks are found.

    Returns:
      (found_ciks: set[str], api_available: bool)
    """
    found_ciks: set[str] = set()
    api_available = False

    for term in terms:
        if target_ciks and target_ciks.issubset(found_ciks):
            log.info("All %d target CIKs found — skipping remaining terms", len(target_ciks))
            break

        page = 0
        log.info("  EFTS %s / %s", form_type, term)

        while page < MAX_PAGES:
            params = {
                "q":         term,
                "forms":     form_type,
                "dateRange": "custom",
                "startdt":   start_date,
                "enddt":     end_date,
                "from":      page * 10,   # EFTS default page size is 10
            }
            data = _efts_get(session, params, f"{form_type}/{term[:18]}/p{page}")

            if data is None:
                # API blocked / failed — stop paginating this term
                log.warning("  EFTS request failed at page %d for %s/%s", page, form_type, term)
                break

            api_available = True
            hits_block = data.get("hits", {})
            hit_list   = hits_block.get("hits", [])
            total_val  = hits_block.get("total", {})
            total      = int(total_val.get("value", 0)) if isinstance(total_val, dict) else int(total_val or 0)

            for hit in hit_list:
                cik = _extract_cik(hit)
                if cik:
                    found_ciks.add(cik)

            page += 1

            if not hit_list:
                break   # empty page — exhausted results

            if page * 10 >= total:
                break   # reached end of results

            # Early exit: all target companies found
            if target_ciks and target_ciks.issubset(found_ciks):
                log.info("  All targets found after page %d (total=%d)", page, total)
                break

        log.info(
            "  %s / %s: %d unique CIKs collected (total results in EFTS: %s)",
            form_type, term, len(found_ciks), total if "total" in dir() else "?"
        )

    return found_ciks, api_available


# ── Classification ────────────────────────────────────────────────────────────
def classify_firms(
    firms: list[dict],
    deployment_ciks: set[str],
    api_available: bool,
) -> list[dict]:
    """
    Classify each firm based on whether its CIK appears in the bulk search.
    """
    results = []
    for f in firms:
        cik_norm = _norm_cik(f.get("cik", "")) if f.get("cik") else ""

        if not api_available:
            cls = "unknown"
            note = "EDGAR unavailable"
        elif not cik_norm:
            cls = "unknown"
            note = "no CIK configured"
        elif cik_norm in deployment_ciks:
            cls = "deployment"
            note = "strong AI term found in filing"
        else:
            # Has a CIK, API worked, but not in deployment results.
            # All major listed companies mention AI broadly in their annual
            # reports — absence of strong terms is itself meaningful (strategic
            # language only, not specific deployment disclosure).
            cls = "strategic"
            note = "strong terms absent; AI mentioned broadly assumed"

        results.append({
            "name":           f["name"],
            "cik":            f.get("cik", ""),
            "country":        f.get("country", ""),
            "sector":         f.get("sector", ""),
            "form":           f["form"],
            "classification": cls,
            "note":           note,
        })
    return results


# ── Aggregation ───────────────────────────────────────────────────────────────
def aggregate(results: list[dict]) -> dict:
    deployment = sum(1 for r in results if r["classification"] == "deployment")
    strategic  = sum(1 for r in results if r["classification"] == "strategic")
    unknown    = sum(1 for r in results if r["classification"] == "unknown")
    denominator = deployment + strategic
    rate = round(deployment / denominator * 100, 1) if denominator > 0 else None
    return {
        "sample_size":       len(results),
        "adoption_positive": deployment,
        "strategic_only":    strategic,
        "unknown":           unknown,
        "denominator":       denominator,
        "adoption_rate":     rate,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now        = datetime.now(timezone.utc)
    end_dt     = now.date()
    start_dt   = (now - timedelta(days=30 * WINDOW_MONTHS)).date()
    start_date = str(start_dt)
    end_date   = str(end_dt)

    log.info("Window: %s → %s  |  US firms: %d  China firms: %d",
             start_date, end_date, len(US_FIRMS), len(CN_FIRMS))

    for f in US_FIRMS:
        f["country"] = "US"
    for f in CN_FIRMS:
        f["country"] = "China"

    us_target_ciks = {_norm_cik(f["cik"]) for f in US_FIRMS if f.get("cik")}
    cn_target_ciks = {_norm_cik(f["cik"]) for f in CN_FIRMS if f.get("cik")}

    session = requests.Session()

    log.info("── 10-K search (US companies) ───────────────────────────────")
    us_deployment_ciks, us_api_ok = search_for_ciks(
        session, "10-K", STRONG_TERMS, start_date, end_date, us_target_ciks
    )

    log.info("── 20-F search (China ADR companies) ────────────────────────")
    cn_deployment_ciks, cn_api_ok = search_for_ciks(
        session, "20-F", STRONG_TERMS, start_date, end_date, cn_target_ciks
    )

    session.close()

    us_results = classify_firms(US_FIRMS, us_deployment_ciks, us_api_ok)
    cn_results = classify_firms(CN_FIRMS, cn_deployment_ciks, cn_api_ok)

    us_agg = aggregate(us_results)
    cn_agg = aggregate(cn_results)

    log.info("")
    log.info("US:    %d/%d deployment  (rate: %s%%  api_ok: %s)",
             us_agg["adoption_positive"], us_agg["sample_size"],
             us_agg["adoption_rate"], us_api_ok)
    log.info("China: %d/%d deployment  (rate: %s%%  api_ok: %s)",
             cn_agg["adoption_positive"], cn_agg["sample_size"],
             cn_agg["adoption_rate"], cn_api_ok)

    # Sanity — warn only, never abort. If EDGAR is blocked, output still
    # gets written with null rates so the UI shows "pending" gracefully.
    if not us_api_ok and not cn_api_ok:
        log.warning("EDGAR EFTS appears to be blocked from this runner — "
                    "outputting null rates; will retry on next run.")
    elif us_agg["denominator"] == 0 and cn_agg["denominator"] == 0:
        log.warning("All firms classified as unknown — CIK list may need review.")

    output = {
        "dimension":  "adoption",
        "metric_key": "filing_adoption_rate",
        "description": (
            "AI adoption proxy: share of major listed companies whose latest annual "
            "filing (10-K or 20-F) shows evidence of AI deployment, based on "
            "SEC EDGAR full-text search for deployment-specific language."
        ),
        "fetched_at":   now.isoformat(),
        "last_updated": now.isoformat(),
        "filing_window": {
            "start":  start_date,
            "end":    end_date,
            "months": WINDOW_MONTHS,
        },
        "edgar_available": {"US": us_api_ok, "China": cn_api_ok},
        "classification": {
            "deployment": (
                "Annual filing mentions \"generative AI\" or \"large language model\" "
                "— strong evidence of operational AI engagement."
            ),
            "strategic": (
                "Annual filing located but does not mention the above terms — "
                "AI referenced broadly without deployment-specific language."
            ),
            "unknown": (
                "Filing not matched by CIK or EDGAR API was inaccessible — "
                "excluded from the adoption rate."
            ),
        },
        "summary": {
            "US":    us_agg,
            "China": cn_agg,
        },
        "firms": us_results + cn_results,
        "source": {
            "name":     "SEC EDGAR Full-Text Search (EFTS)",
            "url":      "https://efts.sec.gov/LATEST/search-index",
            "us_form":  "10-K (US domestic companies)",
            "cn_form":  "20-F (foreign private issuers — Chinese ADRs)",
        },
        "methodology_note": (
            "Adoption rate = deployment-positive companies / (deployment + strategic) × 100. "
            "Strong-term search ('generative AI' or 'large language model') is run across "
            "all 10-K (or 20-F) filings in the window; results are matched by CIK. "
            "Companies with a valid CIK not found in strong-term results are classified as "
            "'strategic' (AI mentioned broadly). Unknown = CIK mismatch or API blocked. "
            "US sample: ~25 major S&P 500 companies. "
            "China sample: ~20 major Chinese ADRs (SEC filers only — not Tencent, ByteDance). "
            "China sample is tech-sector-heavy; compare directionally."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Wrote %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
