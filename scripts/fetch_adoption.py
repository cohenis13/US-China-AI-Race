#!/usr/bin/env python3
"""
Fetch AI Adoption proxy data from public government procurement databases.

WHAT THIS MEASURES
  Visible institutional AI deployment — specifically, government procurement
  actions (contract awards and tender notices) for AI-related systems and
  services. A procurement order is a stronger adoption signal than a mention,
  a posting, or a plan: it means an institution is actively acquiring AI.

PRIMARY SOURCE — United States: USASpending.gov
  - Official US federal spending data (OMB / Treasury)
  - No API key required
  - Counts federal contract awards whose descriptions match AI-related keywords
  - Award types A–D (contracts only — excludes grants, loans, cooperative agreements)
  - Rolling 12-month window

PRIMARY SOURCE — China: CCGP (中国政府采购网 / China Government Procurement Network)
  - China's official central-government procurement portal
  - Best-effort HTML scraping via public search interface
  - GitHub Actions runners (Azure US East IPs) are frequently blocked by CCGP
  - If inaccessible, outputs null with an explanatory note — does NOT abort
  - Keyword: 人工智能 (artificial intelligence)

KNOWN LIMITATION — TRANSPARENCY ASYMMETRY
  US procurement data is substantially more transparent and automatable than
  Chinese procurement data. Observed US/China ratios therefore reflect this
  asymmetry and should NOT be interpreted as proportional measures of actual
  AI adoption rates. This is documented in the output methodology_note.

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

# ── API Endpoints ──────────────────────────────────────────────────────────────
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
CCGP_SEARCH_URL = "http://search.ccgp.gov.cn/bxsearch"

US_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker/1.0 "
        "(public research dashboard; github.com/cohenis13/US-China-AI-Race)"
    ),
    "Content-Type": "application/json",
    "Accept":       "application/json",
}

# Use browser-like headers for CCGP to minimize IP-based rejection
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


# ── Date helpers ──────────────────────────────────────────────────────────────
def date_range() -> tuple[str, str]:
    """Return (start_date, end_date) for the rolling window (YYYY-MM-DD)."""
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=WINDOW_DAYS)
    return str(start), str(end)


# ── US Procurement: USASpending.gov ───────────────────────────────────────────
def fetch_us_procurement(start_date: str, end_date: str) -> dict:
    """
    Fetch US federal AI contract award count from USASpending.gov.

    Uses the /api/v2/search/spending_by_award/ endpoint.
    The 'keywords' filter applies OR logic — a single query returns a
    deduplicated count of all contracts matching any of US_KEYWORDS.
    Award type codes A–D = contracts (Purchase Orders, Delivery Orders,
    BPA Calls, Definitive Contracts). Grants and loans excluded.

    Returns dict with keys: count, examples, available, confidence
    """
    payload = {
        "filters": {
            "keywords":         US_KEYWORDS,       # OR — single deduped query
            "time_period":      [{"start_date": start_date, "end_date": end_date}],
            "award_type_codes": ["A", "B", "C", "D"],   # contracts only
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

        # Extract total count — try multiple possible field paths defensively
        total_meta = data.get("total_metadata") or {}
        count = (
            total_meta.get("count")
            or total_meta.get("total")
            or len(data.get("results", []))
        )
        count = int(count) if count else 0

        results  = data.get("results", [])
        log.info(
            "US procurement: %d AI-related federal contract awards (last %d days)",
            count, WINDOW_DAYS,
        )

        # Normalize example records
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
            "available":  True,
            "confidence": "medium",
            # "medium" because keyword matching captures AI-related contracts
            # broadly (includes AI consulting, tools, research), not only
            # confirmed operational deployments.
        }

    except Exception as e:
        log.error("US procurement fetch failed: %s", e)
        return {
            "count":      0,
            "examples":   [],
            "available":  False,
            "confidence": "low",
            "error":      str(e),
        }


# ── China Procurement: CCGP ────────────────────────────────────────────────────
def _parse_ccgp_total(html: str) -> int | None:
    """
    Extract total result count from a CCGP search results page.

    CCGP displays totals in multiple possible patterns depending on result
    volume and page layout. We try patterns from most to least specific.
    Returns None if no count can be reliably extracted.
    """
    patterns = [
        r'共\s*找到\s*([\d,]+)\s*条',      # 共找到X条
        r'共\s*([\d,]+)\s*条\s*信息',       # 共X条信息
        r'共\s*([\d,]+)\s*条',              # 共X条
        r'找到相关信息\s*([\d,]+)\s*条',    # 找到相关信息X条
        r'结果共\s*([\d,]+)\s*条',          # 结果共X条
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
    Single keyword (人工智能) to avoid cross-keyword double-counting
    that cannot be deduplicated via HTML scraping.

    Returns dict with keys: count (or None), available, confidence, note
    """
    # CCGP uses colon-separated dates
    start_ccgp = start_date.replace("-", ":")
    end_ccgp   = end_date.replace("-", ":")

    params = {
        "searchtype": "1",
        "bidSort":    "0",
        "kw":         CN_KEYWORD_ZH,
        "start_time": start_ccgp,
        "end_time":   end_ccgp,
        "timeType":   "6",      # by announcement date
        "dbselect":   "bidx",   # procurement notice index
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

        # Validate response is HTML, not a redirect or error page
        ct = resp.headers.get("content-type", "")
        if len(resp.content) < 500:
            raise ValueError(
                f"Response too short ({len(resp.content)} bytes) — likely blocked or login redirect"
            )
        if "html" not in ct and "text" not in ct:
            raise ValueError(f"Unexpected content-type: {ct}")

        # Decode — CCGP often uses GB18030 or GBK encoding
        # Try UTF-8 first, fall back to GB18030
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
                "available":  False,
                "confidence": "unavailable",
                "note": (
                    "CCGP returned a response but the total count could not be parsed. "
                    "The page structure may have changed. China count is unavailable for this snapshot."
                ),
            }

        log.info("CN procurement: %d notices for '%s' (last %d days)", count, CN_KEYWORD_ZH, WINDOW_DAYS)
        return {
            "count":      count,
            "available":  True,
            "confidence": "low",
            # "low" because:
            # 1. Only central-level procurement; sub-national excluded
            # 2. HTML scraping is fragile and may undercount
            # 3. Reports only notices matching one keyword — broader AI
            #    procurement may use different Chinese terminology
            "note": (
                "Central-government procurement notices only (CCGP). "
                "Sub-national (provincial / municipal) procurement not captured. "
                f"Keyword: '{CN_KEYWORD_ZH}' (artificial intelligence). "
                "Likely significant undercount of total government AI procurement. "
                "China's procurement reporting is substantially less automatable "
                "than US federal procurement data."
            ),
        }

    except requests.exceptions.Timeout:
        log.warning("CCGP: timed out — server may be blocking this IP (GitHub Actions = Azure US East)")
    except requests.exceptions.ConnectionError as e:
        log.warning("CCGP: connection error — %s", e)
    except Exception as e:
        log.warning("CCGP: %s", e)

    return {
        "count":      None,
        "available":  False,
        "confidence": "unavailable",
        "note": (
            "CCGP was inaccessible from the automated runner. "
            "GitHub Actions (Azure US East IPs) are commonly blocked by CCGP. "
            "China government procurement data is not available for this snapshot. "
            "This is a known infrastructure limitation, not a data absence."
        ),
    }


# ── Sanity checks ──────────────────────────────────────────────────────────────
def sanity_check(us_data: dict) -> None:
    """Abort if US data is clearly broken (the primary required signal)."""
    if not us_data["available"]:
        log.error("FAIL: US procurement data unavailable — aborting")
        sys.exit(1)
    if us_data["count"] == 0:
        log.error(
            "FAIL: US procurement count = 0 over %d days — "
            "keyword filter may be broken or API changed",
            WINDOW_DAYS,
        )
        sys.exit(1)
    log.info("Sanity check passed: US count = %d", us_data["count"])


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    start_date, end_date = date_range()
    log.info("Window: %s → %s (%d days)", start_date, end_date, WINDOW_DAYS)

    log.info("Fetching US procurement data (USASpending.gov) …")
    us_data = fetch_us_procurement(start_date, end_date)

    log.info("Fetching China procurement data (CCGP) …")
    cn_data = fetch_cn_procurement(start_date, end_date)

    sanity_check(us_data)

    if not cn_data["available"]:
        log.warning(
            "China data unavailable — output will reflect US data only. "
            "China count will be null (not zero)."
        )

    output = {
        "dimension":    "adoption",
        "metric_key":   "ai_procurement_notices",
        "description": (
            "Count of AI-related government procurement contract awards and notices "
            "over a rolling 12-month window. "
            "US: federal contract awards from USASpending.gov. "
            "China: central government notices from CCGP (best-effort). "
            "A proxy for visible institutional AI deployment intent — "
            "not a complete or symmetric measure of adoption."
        ),
        "fetched_at":    datetime.now(timezone.utc).isoformat(),
        "window_days":   WINDOW_DAYS,
        "start_date":    start_date,
        "end_date":      end_date,
        "search_keywords": {
            "US":    US_KEYWORDS,
            "China": [CN_KEYWORD_ZH],
        },
        "summary": {
            "US": {
                "procurement_count": us_data["count"],
                "source":            "USASpending.gov",
                "available":         us_data["available"],
                "confidence":        us_data["confidence"],
            },
            "China": {
                "procurement_count": cn_data.get("count"),    # may be null
                "source":            "CCGP (中国政府采购网)",
                "available":         cn_data["available"],
                "confidence":        cn_data["confidence"],
                "note":              cn_data.get("note", ""),
            },
        },
        "top_examples": us_data.get("examples", []),
        "source": {
            "primary_us": {
                "name": "USASpending.gov",
                "url":  "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                "note": (
                    "Official US federal spending data (OMB / Treasury). "
                    "Counts federal contract awards (types A–D) where the description "
                    "matches AI-related keywords using OR logic. "
                    "No API key required. Covers federal government only."
                ),
            },
            "primary_cn": {
                "name": "CCGP (中国政府采购网)",
                "url":  "http://www.ccgp.gov.cn",
                "note": (
                    "China's official central-government procurement portal. "
                    "Scraped via public search interface. "
                    "May be inaccessible from non-Chinese IP addresses. "
                    "Covers central-level procurement only."
                ),
            },
        },
        "methodology_note": (
            "Government procurement actions are used as an adoption proxy because "
            "they represent a binding institutional decision to acquire AI — "
            "stronger than mentions, job postings, or expressed intent. "
            "US: keyword search across federal contract award descriptions via "
            "the USASpending.gov API (official OMB/Treasury data, no auth required). "
            "China: keyword search on CCGP, China's central procurement portal, "
            "via public HTML search interface. "
            "The two sources differ in scope, reporting norms, and accessibility. "
            "US data covers the full federal government with high automation reliability. "
            "China data covers only the central government and may be inaccessible "
            "from non-Chinese IP addresses (GitHub Actions runners are US-based Azure). "
            "Counts reflect procurement orders placed, not confirmed deployment outcomes. "
            "Updated daily."
        ),
        "caveats": (
            "1. Scope asymmetry: US covers federal government only (not state/local/private). "
            "China covers central CCGP only (not provincial/local/military). "
            "2. Transparency asymmetry: US procurement is far more transparent and "
            "automatable than China's. The observed US/China ratio reflects this gap, "
            "not necessarily a proportional difference in actual AI adoption. "
            "3. Keyword coverage: AI-related keyword matching is broad — counts include "
            "contracts for AI research, consulting, and tools alongside operational deployment. "
            "4. China availability: CCGP frequently blocks non-Chinese IPs. When blocked, "
            "China count is null (not zero) — absence of data ≠ absence of procurement. "
            "5. Both figures measure observable procurement signals, not deployment outcomes."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output: %s", OUTPUT_FILE)
    log.info("Window: %s → %s", start_date, end_date)
    log.info(
        "  US:    %d contracts  (confidence: %s)",
        us_data["count"], us_data["confidence"],
    )
    log.info(
        "  China: %s notices    (confidence: %s)",
        cn_data.get("count", "N/A"), cn_data["confidence"],
    )
    log.info("  Examples included: %d", len(output["top_examples"]))


if __name__ == "__main__":
    main()
