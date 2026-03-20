#!/usr/bin/env python3
"""
Fetch AI Adoption proxy data from two public signals.

SIGNAL 1 — Government Procurement
  US:    USASpending.gov federal contract awards (keyword search, no auth)
  China: CCGP central procurement notices (HTML scraping, best-effort)

SIGNAL 2 — Public Company Filings (SEC EDGAR)
  US proxy:    10-K filings mentioning "AI deployment" (US domestic companies)
  China proxy: 20-F filings mentioning "AI deployment" (foreign private
               issuers — primarily Chinese ADRs on US exchanges, not exclusively
               Chinese companies)

KNOWN LIMITATION — TRANSPARENCY ASYMMETRY
  US procurement data is substantially more transparent and automatable than
  Chinese procurement data. CCGP frequently blocks non-Chinese IP addresses
  (GitHub Actions runners are Azure US East). When blocked, China procurement
  count is null — absence of data ≠ absence of procurement.

  SEC EDGAR 20-F filings are a China proxy only: they cover all foreign
  companies listed on US exchanges, with Chinese ADRs as the dominant segment.
  This overstates "China" relative to the 10-K US figure.

Outputs to data/adoption.json.

Usage:
    pip install requests
    python scripts/fetch_adoption.py
"""

import json
import re
import sys
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
WINDOW_DAYS     = 365   # rolling 12-month window
REQUEST_TIMEOUT = 30    # seconds per request
MAX_EXAMPLES    = 10    # top US examples to include in output

# US keywords — passed as a single OR query, so no double-counting within US
US_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "generative AI",
    "large language model",
    "AI system",
]

# China keyword — single keyword to avoid cross-keyword double-counting in
# CCGP results (which cannot be server-side deduplicated via scraping)
CN_KEYWORD_ZH = "人工智能"   # artificial intelligence

# EDGAR exact-phrase query for company filing signal
EDGAR_QUERY = "AI deployment"

# ── API Endpoints ─────────────────────────────────────────────────────────────
USASPENDING_URL  = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
CCGP_SEARCH_URL  = "http://search.ccgp.gov.cn/bxsearch"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

US_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker/1.0 "
        "(public research dashboard; github.com/cohenis13/US-China-AI-Race)"
    ),
    "Content-Type": "application/json",
    "Accept":       "application/json",
}

# Use browser-like headers for CCGP to minimise IP-based rejection
CN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

EDGAR_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker/1.0 "
        "(public research dashboard; github.com/cohenis13/US-China-AI-Race)"
    ),
    "Accept": "application/json",
}


# ── Date helpers ──────────────────────────────────────────────────────────────
def date_range() -> tuple[str, str]:
    """Return (start_date, end_date) for the rolling window (YYYY-MM-DD)."""
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=WINDOW_DAYS)
    return str(start), str(end)


# ── Signal 1a: US Procurement — USASpending.gov ───────────────────────────────
def fetch_us_procurement(start_date: str, end_date: str) -> dict:
    """
    Fetch US federal AI contract award count from USASpending.gov.

    Uses the /api/v2/search/spending_by_award/ endpoint.
    The 'keywords' filter applies OR logic — a single query returns a
    deduplicated count of all contracts matching any of US_KEYWORDS.
    Award type codes A–D = contracts only (excludes grants, loans, etc.).

    Returns dict with: count, examples, status, confidence
    Status values: "ok" | "error"
    """
    payload = {
        "filters": {
            "keywords":         US_KEYWORDS,
            "time_period":      [{"start_date": start_date, "end_date": end_date}],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Start Date",
            "Awarding Agency",
            "Awarding Sub Agency",
        ],
        "page":  1,
        "limit": MAX_EXAMPLES,
        "sort":  "Award Amount",
        "order": "desc",
    }

    try:
        resp = requests.post(
            USASPENDING_URL,
            json=payload,
            headers=US_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        total_meta = data.get("total_metadata") or {}
        count = (
            total_meta.get("count")
            or total_meta.get("total")
            or len(data.get("results", []))
        )
        count = int(count) if count else 0

        results = data.get("results", [])
        log.info("US procurement: %d federal AI contract awards (last %d days)", count, WINDOW_DAYS)

        examples = []
        for r in results[:MAX_EXAMPLES]:
            agency = r.get("Awarding Agency") or r.get("Awarding Sub Agency") or ""
            examples.append({
                "award_id":  r.get("Award ID", ""),
                "recipient": r.get("Recipient Name", ""),
                "amount":    r.get("Award Amount"),
                "date":      r.get("Start Date", ""),
                "agency":    agency,
                "country":   "US",
            })

        return {
            "count":      count,
            "examples":   examples,
            "status":     "ok",
            "confidence": "medium",
            "note": (
                "Federal contract awards (types A–D) whose descriptions match AI keywords "
                "(OR logic, deduplicated). Federal government only — excludes state, "
                "local, and private sector."
            ),
        }

    except Exception as e:
        log.error("US procurement fetch failed: %s", e)
        return {
            "count":      None,
            "examples":   [],
            "status":     "error",
            "confidence": "low",
            "note":       f"Fetch failed: {e}",
        }


# ── Signal 1b: China Procurement — CCGP ───────────────────────────────────────
def _parse_ccgp_total(html: str) -> int | None:
    """
    Extract total result count from a CCGP search results page.
    Tries patterns from most to least specific. Returns None if not found.
    """
    patterns = [
        r'共\s*找到\s*([\d,]+)\s*条',
        r'共\s*([\d,]+)\s*条\s*信息',
        r'共\s*([\d,]+)\s*条',
        r'找到相关信息\s*([\d,]+)\s*条',
        r'结果共\s*([\d,]+)\s*条',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def fetch_cn_procurement(start_date: str, end_date: str) -> dict:
    """
    Fetch China government AI procurement notice count from CCGP.

    CCGP date format: YYYY:MM:DD (colon-separated, not hyphen).
    Single keyword (人工智能) to avoid cross-keyword double-counting.

    Status values: "ok" | "partial" | "blocked" | "error"
    """
    start_ccgp = start_date.replace("-", ":")
    end_ccgp   = end_date.replace("-", ":")

    params = {
        "searchtype": "1",
        "bidSort":    "0",
        "kw":         CN_KEYWORD_ZH,
        "start_time": start_ccgp,
        "end_time":   end_ccgp,
        "timeType":   "6",
        "dbselect":   "bidx",
        "pinMu":      "0",
        "bidType":    "0",
    }

    try:
        resp = requests.get(
            CCGP_SEARCH_URL,
            params=params,
            headers=CN_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        ct = resp.headers.get("content-type", "")
        if len(resp.content) < 500:
            raise ValueError(
                f"Response too short ({len(resp.content)} bytes) — likely blocked or redirect"
            )
        if "html" not in ct and "text" not in ct:
            raise ValueError(f"Unexpected content-type: {ct}")

        try:
            html = resp.content.decode("utf-8")
        except UnicodeDecodeError:
            html = resp.content.decode("gb18030", errors="replace")

        count = _parse_ccgp_total(html)

        if count is None:
            log.warning(
                "CCGP: count not found in HTML (len=%d, status=%d) — "
                "page structure may have changed",
                len(html), resp.status_code,
            )
            return {
                "count":      None,
                "status":     "partial",
                "confidence": "unavailable",
                "note": (
                    "CCGP returned a response but the total count could not be parsed. "
                    "The page structure may have changed. China count is unavailable for this snapshot."
                ),
            }

        log.info("CN procurement: %d notices for '%s' (last %d days)", count, CN_KEYWORD_ZH, WINDOW_DAYS)
        return {
            "count":      count,
            "status":     "ok",
            "confidence": "low",
            "note": (
                f"Central-government procurement notices only (CCGP). "
                f"Keyword: '{CN_KEYWORD_ZH}' (artificial intelligence). "
                "Sub-national (provincial / municipal) procurement not captured. "
                "Likely significant undercount of total government AI procurement."
            ),
        }

    except requests.exceptions.Timeout:
        log.warning("CCGP: timed out — likely blocked (GitHub Actions = Azure US East IPs)")
    except requests.exceptions.ConnectionError as e:
        log.warning("CCGP: connection error — %s", e)
    except Exception as e:
        log.warning("CCGP: %s", e)

    return {
        "count":      None,
        "status":     "blocked",
        "confidence": "unavailable",
        "note": (
            "CCGP was inaccessible from the automated runner. "
            "GitHub Actions (Azure US East IPs) are commonly blocked by CCGP. "
            "This is a known infrastructure limitation — null ≠ zero procurement."
        ),
    }


# ── Signal 2: Company Filings — SEC EDGAR ─────────────────────────────────────
def fetch_edgar(form_type: str, start_date: str, end_date: str) -> dict:
    """
    Count SEC EDGAR filings of a given form type mentioning the exact phrase
    "AI deployment" in the specified date range.

    form_type: "10-K" (US domestic companies, filed annually)
               "20-F" (foreign private issuers — primarily Chinese ADRs on US
                       exchanges, not exclusively Chinese companies)

    Uses the public EFTS full-text search API — no authentication required.

    Status values: "ok" (10-K) | "partial" (20-F, proxy coverage) | "error"
    """
    params = {
        "q":         f'"{EDGAR_QUERY}"',
        "forms":     form_type,
        "dateRange": "custom",
        "startdt":   start_date,
        "enddt":     end_date,
    }
    label     = f"EDGAR {form_type}"
    is_proxy  = (form_type == "20-F")

    try:
        resp = requests.get(
            EDGAR_SEARCH_URL,
            params=params,
            headers=EDGAR_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # Response shape: {"hits": {"total": {"value": N, "relation": "eq"}, "hits": [...]}}
        # Some older versions return {"hits": {"total": N, ...}}
        hits_block = data.get("hits", {})
        total      = hits_block.get("total")
        if isinstance(total, dict):
            count = int(total.get("value", 0))
        elif total is not None:
            count = int(total)
        else:
            raise ValueError(f"Unexpected response shape — keys: {list(data.keys())}")

        log.info('%s: %d filings with "%s" (last %d days)', label, count, EDGAR_QUERY, WINDOW_DAYS)

        if is_proxy:
            return {
                "count":      count,
                "status":     "partial",
                "confidence": "low",
                "note": (
                    "20-F filings cover all foreign private issuers listed on US exchanges. "
                    "Chinese ADRs are the largest segment but this is not exclusively China. "
                    "Treat as a directional China proxy — likely overstates China vs the "
                    "10-K US figure. Counts filings (one per company per year), "
                    "not deployment instances."
                ),
            }
        else:
            return {
                "count":      count,
                "status":     "ok",
                "confidence": "medium",
                "note": (
                    f'US domestic company 10-K annual reports mentioning "{EDGAR_QUERY}" '
                    "(exact phrase). Counts filings (one per company per year), not "
                    "deployment instances. Excludes companies that do not file with SEC."
                ),
            }

    except Exception as e:
        log.error("%s fetch failed: %s", label, e)
        return {
            "count":      None,
            "status":     "error",
            "confidence": "low",
            "note":       f"Fetch failed: {e}",
        }


# ── Sanity checks ─────────────────────────────────────────────────────────────
def sanity_check(us_proc: dict, us_edgar: dict) -> None:
    """Abort if all primary US signals failed, or if procurement count is zero."""
    both_errored = (us_proc["status"] == "error" and us_edgar["status"] == "error")
    if both_errored:
        log.error("FAIL: Both US signals returned errors — aborting")
        sys.exit(1)

    if us_proc["status"] == "ok":
        if (us_proc.get("count") or 0) == 0:
            log.error(
                "FAIL: US procurement count = 0 over %d days — "
                "keyword filter or API may be broken",
                WINDOW_DAYS,
            )
            sys.exit(1)
        log.info("Sanity check: US procurement = %d (ok)", us_proc["count"])

    if us_edgar["status"] in ("ok", "partial"):
        log.info("Sanity check: US EDGAR 10-K = %d (ok)", us_edgar.get("count", 0))


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    start_date, end_date = date_range()
    log.info("Window: %s → %s (%d days)", start_date, end_date, WINDOW_DAYS)

    log.info("Signal 1a: US procurement (USASpending.gov) …")
    us_proc  = fetch_us_procurement(start_date, end_date)

    log.info("Signal 1b: China procurement (CCGP) …")
    cn_proc  = fetch_cn_procurement(start_date, end_date)

    log.info('Signal 2a: US company filings (EDGAR 10-K, "%s") …', EDGAR_QUERY)
    us_edgar = fetch_edgar("10-K", start_date, end_date)

    log.info('Signal 2b: China proxy filings (EDGAR 20-F, "%s") …', EDGAR_QUERY)
    cn_edgar = fetch_edgar("20-F", start_date, end_date)

    sanity_check(us_proc, us_edgar)

    if cn_proc["status"] in ("blocked", "error"):
        log.warning(
            "China procurement unavailable (status: %s) — null ≠ zero procurement.",
            cn_proc["status"],
        )

    output = {
        "dimension":  "adoption",
        "metric_key": "ai_adoption_signals",
        "description": (
            "Two-signal proxy for AI adoption: (1) government procurement actions "
            "(contract awards and tender notices) and (2) public company annual filing "
            "mentions of AI deployment. Neither signal is a complete or symmetric measure. "
            "US data is substantially more transparent and automatable than China data."
        ),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW_DAYS,
        "start_date":  start_date,
        "end_date":    end_date,
        "signals": {
            "government_procurement": {
                "description": (
                    "Government AI contract awards and procurement notices — binding "
                    "institutional decisions to acquire AI. Stronger adoption signal "
                    "than mentions or expressed intent."
                ),
                "keywords": {
                    "US":    US_KEYWORDS,
                    "China": [CN_KEYWORD_ZH],
                },
                "US": {
                    "count":      us_proc.get("count"),
                    "status":     us_proc["status"],
                    "confidence": us_proc["confidence"],
                    "source":     "USASpending.gov",
                    "note":       us_proc.get("note", ""),
                },
                "China": {
                    "count":      cn_proc.get("count"),
                    "status":     cn_proc["status"],
                    "confidence": cn_proc["confidence"],
                    "source":     "CCGP (中国政府采购网)",
                    "note":       cn_proc.get("note", ""),
                },
            },
            "company_filings": {
                "description": (
                    f'Public company annual filings mentioning "{EDGAR_QUERY}" '
                    "(exact phrase) via SEC EDGAR full-text search. "
                    "US: 10-K (domestic companies). "
                    "China proxy: 20-F (foreign private issuers — primarily Chinese ADRs)."
                ),
                "query": EDGAR_QUERY,
                "US": {
                    "count":      us_edgar.get("count"),
                    "status":     us_edgar["status"],
                    "confidence": us_edgar["confidence"],
                    "source":     "SEC EDGAR (10-K filings)",
                    "note":       us_edgar.get("note", ""),
                },
                "China_proxy": {
                    "count":      cn_edgar.get("count"),
                    "status":     cn_edgar["status"],
                    "confidence": cn_edgar["confidence"],
                    "source":     "SEC EDGAR (20-F filings)",
                    "note":       cn_edgar.get("note", ""),
                },
            },
        },
        "top_examples": us_proc.get("examples", []),
        "source": {
            "usaspending": {
                "name": "USASpending.gov",
                "url":  "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                "note": "Official US federal spending data (OMB / Treasury). No API key required.",
            },
            "ccgp": {
                "name": "CCGP (中国政府采购网)",
                "url":  "http://www.ccgp.gov.cn",
                "note": "China's official central-government procurement portal. HTML scraping, best-effort.",
            },
            "edgar": {
                "name": "SEC EDGAR Full-Text Search (EFTS)",
                "url":  "https://efts.sec.gov/LATEST/search-index",
                "note": "Public full-text search across SEC filings. No API key required.",
            },
        },
        "methodology_note": (
            "Signal 1 (Government Procurement): Procurement actions represent binding "
            "institutional decisions to acquire AI — stronger signal than mentions or plans. "
            "US: keyword OR search across federal contract award descriptions via the "
            "USASpending.gov API (official OMB/Treasury data). "
            "China: single-keyword search on CCGP public HTML interface (best-effort, "
            "often blocked from US IP addresses). "
            "Signal 2 (Company Filings): SEC EDGAR full-text search for the exact phrase "
            f'"{EDGAR_QUERY}" in annual reports. '
            "10-K = US domestic companies; 20-F = foreign private issuers listed on US "
            "exchanges (primarily Chinese ADRs — not exclusively China). "
            "Counts filings per year, not deployment instances. "
            "Updated daily via GitHub Actions."
        ),
        "caveats": (
            "1. Scope asymmetry: US = federal government + US-listed companies. "
            "China = central CCGP notices (often blocked from US IPs) + ADR proxy (non-exclusive). "
            "2. Transparency asymmetry: US data is far more automatable. "
            "Observed US/China ratios reflect this gap, not proportional adoption differences. "
            "3. CCGP null = inaccessible from runner, not zero procurement. "
            "4. 20-F proxy overstates 'China' — includes all foreign private issuers. "
            "5. Counts reflect procurement orders placed / filing mentions, not deployment outcomes."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output: %s", OUTPUT_FILE)
    log.info("Window: %s → %s", start_date, end_date)
    log.info("Signal 1 — Government Procurement:")
    log.info("  US:           %s contracts  (status: %s)", us_proc.get("count"), us_proc["status"])
    log.info("  China:        %s notices    (status: %s)", cn_proc.get("count"), cn_proc["status"])
    log.info("Signal 2 — Company Filings (EDGAR):")
    log.info("  US 10-K:      %s filings    (status: %s)", us_edgar.get("count"), us_edgar["status"])
    log.info("  20-F proxy:   %s filings    (status: %s)", cn_edgar.get("count"), cn_edgar["status"])


if __name__ == "__main__":
    main()
