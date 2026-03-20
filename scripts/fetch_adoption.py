#!/usr/bin/env python3
"""
Fetch AI adoption proxy data — government procurement signal.

WHAT THIS MEASURES
  Government procurement of AI-related contracts and notices, used as a
  proxy for institutional AI deployment activity. This is NOT a total
  adoption census.

SIGNAL — GOVERNMENT PROCUREMENT
  US:    USASpending.gov federal contract awards — keyword match in award
         descriptions. The time_period filter applies to action_date (the
         transaction date). Multi-year contracts appear if a procurement
         action fell in the window, even if the contract originated earlier.
  China: CCGP (中国政府采购网) — HTML scraping, best-effort.
         GitHub Actions (Azure US East IPs) are frequently blocked.
         When blocked: status="blocked", count=null. null ≠ zero.

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
WINDOW_DAYS     = 365
REQUEST_TIMEOUT = 30
MAX_EXAMPLES    = 10

US_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "generative AI",
    "large language model",
    "AI system",
]
CN_KEYWORD_ZH = "人工智能"

# ── API endpoints ─────────────────────────────────────────────────────────────
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
CCGP_SEARCH_URL = "http://search.ccgp.gov.cn/bxsearch"

US_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker (non-commercial public research; "
        "github.com/cohenis13/US-China-AI-Race)"
    ),
    "Content-Type": "application/json",
    "Accept":       "application/json",
}
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
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=WINDOW_DAYS)
    return str(start), str(end)


# ── US Government Procurement ─────────────────────────────────────────────────
def fetch_us_procurement(start_date: str, end_date: str) -> dict:
    """
    Count US federal AI contract awards from USASpending.gov.

    time_period filters by action_date (the transaction date), not by
    period_of_performance_start_date. A multi-year contract signed years
    ago appears here if a new procurement action (modification, increment)
    fell within the window. This explains why 'Contract Start' dates in
    examples may predate the window.
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
            "Description",
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

        examples = []
        for r in data.get("results", [])[:MAX_EXAMPLES]:
            agency = r.get("Awarding Agency") or r.get("Awarding Sub Agency") or ""
            desc   = r.get("Description") or ""
            examples.append({
                "award_id":       r.get("Award ID", ""),
                "recipient":      r.get("Recipient Name", ""),
                "amount":         r.get("Award Amount"),
                "contract_start": r.get("Start Date", ""),
                "agency":         agency,
                "description":    desc[:100] if desc else "",
                "country":        "US",
            })

        log.info("US procurement: %d federal AI contract awards", count)
        return {
            "count":    count,
            "examples": examples,
            "status":   "ok",
        }

    except Exception as e:
        log.error("US procurement fetch failed: %s", e)
        return {
            "count":    None,
            "examples": [],
            "status":   "error",
        }


# ── China Government Procurement ──────────────────────────────────────────────
def _parse_ccgp_total(html: str) -> int | None:
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
    Count China central-government AI procurement notices from CCGP.
    GitHub Actions (Azure US East IPs) are commonly blocked — status="blocked".
    Blocked ≠ zero procurement.
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

        if len(resp.content) < 500:
            raise ValueError(f"Response too short ({len(resp.content)} bytes) — likely blocked")

        try:
            html = resp.content.decode("utf-8")
        except UnicodeDecodeError:
            html = resp.content.decode("gb18030", errors="replace")

        count = _parse_ccgp_total(html)

        if count is None:
            log.warning("CCGP: count not parseable (len=%d)", len(html))
            return {"count": None, "status": "partial"}

        log.info("CN procurement: %d notices for '%s'", count, CN_KEYWORD_ZH)
        return {"count": count, "status": "ok"}

    except requests.exceptions.Timeout:
        log.warning("CCGP: timed out — likely blocked")
    except requests.exceptions.ConnectionError as e:
        log.warning("CCGP: connection error — %s", e)
    except Exception as e:
        log.warning("CCGP: %s", e)

    return {"count": None, "status": "blocked"}


# ── Sanity check ──────────────────────────────────────────────────────────────
def sanity_check(us_proc: dict) -> None:
    if us_proc["status"] == "error":
        log.error("FAIL: US procurement fetch failed — aborting")
        sys.exit(1)
    if us_proc["status"] == "ok" and (us_proc.get("count") or 0) == 0:
        log.error("FAIL: US procurement count = 0 — keyword filter or API may be broken")
        sys.exit(1)
    log.info("Sanity check OK — US: %s (%s)", us_proc.get("count"), us_proc["status"])


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    start_date, end_date = date_range()
    log.info("Window: %s → %s (%d days)", start_date, end_date, WINDOW_DAYS)

    log.info("US procurement (USASpending.gov) …")
    us_proc = fetch_us_procurement(start_date, end_date)

    log.info("China procurement (CCGP) …")
    cn_proc = fetch_cn_procurement(start_date, end_date)

    sanity_check(us_proc)

    now = datetime.now(timezone.utc).isoformat()

    output = {
        "dimension":   "adoption",
        "metric_key":  "ai_adoption_signals",
        "description": (
            "Government procurement of AI-related contracts as a proxy for "
            "institutional AI deployment activity. Not a total adoption census — "
            "coverage differs across countries due to public reporting systems."
        ),
        "fetched_at":   now,
        "last_updated": now,
        "window_days":  WINDOW_DAYS,
        "start_date":   start_date,
        "end_date":     end_date,

        "procurement": {
            "US": {
                "count":      us_proc.get("count"),
                "status":     us_proc["status"],
                "source":     "USASpending.gov",
                "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                "keywords":   US_KEYWORDS,
                "note": (
                    "Federal contracts (types A–D) with AI keywords in award descriptions. "
                    "Filtered by action_date — contract start dates in examples may predate "
                    "the window for multi-year contracts. Federal only."
                ),
            },
            "China": {
                "count":      cn_proc.get("count"),
                "status":     cn_proc["status"],
                "source":     "CCGP (中国政府采购网)",
                "source_url": "http://search.ccgp.gov.cn/bxsearch",
                "keywords":   [CN_KEYWORD_ZH],
                "note": (
                    "Central-government procurement notices only. "
                    "CCGP is frequently inaccessible from non-Chinese IPs — "
                    "null ≠ zero procurement."
                ),
            },
        },

        "top_examples": us_proc.get("examples", []),
        "examples_note": (
            "Sorted by award amount. 'Contract Start' = period_of_performance_start_date "
            "and may predate the window — contracts appear because a procurement action "
            "occurred within the last 12 months."
        ),

        "source_urls": {
            "usaspending": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            "ccgp":        "http://www.ccgp.gov.cn",
        },

        "methodology_note": (
            "Procurement captures binding institutional decisions to acquire AI systems — "
            "a stronger and more automatable signal than self-reported surveys. "
            "US data covers the full federal government via a public API. "
            "China data covers only central-government notices on CCGP, which is "
            "frequently inaccessible from outside China. "
            "This asymmetry reflects the design of public reporting systems, not analysis choice. "
            "Private-sector AI deployment and sub-national government activity are not captured."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output: %s", OUTPUT_FILE)
    log.info("  US:    %s contracts (%s)", us_proc.get("count"), us_proc["status"])
    log.info("  China: %s notices   (%s)", cn_proc.get("count"), cn_proc["status"])


if __name__ == "__main__":
    main()
