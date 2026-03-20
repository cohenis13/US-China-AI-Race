#!/usr/bin/env python3
"""
Fetch AI Adoption proxy data — two-signal model.

WHAT THIS MEASURES
  Observable AI deployment activity in public records:
  (1) Government procurement orders — binding institutional decisions to acquire AI.
  (2) Corporate annual report disclosures — companies reporting generative AI use.

  This is a proxy for visible deployment, not total adoption.

SIGNAL 1 — GOVERNMENT PROCUREMENT
  US:    USASpending.gov federal contract awards (API, no auth)
         Counts contracts with AI keywords in award descriptions.
         Time window applied via action_date (the transaction date).
  China: CCGP (中国政府采购网) — best-effort HTML scraping.
         GitHub Actions (Azure US East IPs) are frequently blocked.
         When blocked: status="blocked", count=null. Null ≠ zero.

SIGNAL 2 — CORPORATE FILING DISCLOSURES (SEC EDGAR)
  US proxy:    10-K annual reports mentioning "generative AI"
               (covers all US SEC-registered companies).
  China proxy: 20-F annual reports mentioning "generative AI"
               (covers foreign private issuers on US exchanges;
               Chinese ADRs are the dominant segment but not exclusive).
  Query term: "generative AI" — specific to the current AI wave.
              May include companies exploring generative AI, not only
              those with confirmed deployments. See methodology_note.
  Total filers: also queries the EFTS API without a keyword filter to
                compute a deployment-rate denominator.

KNOWN LIMITATIONS
  1. Scope asymmetry: US data is far more transparent and automatable.
  2. CCGP null = access blocked from runner, not zero procurement.
  3. 20-F proxy: Chinese ADRs are the largest segment of 20-F filers,
     but the proxy includes other foreign issuers (European, Korean, etc.).
  4. Procurement count reflects explicit AI keyword mentions in award
     descriptions — likely understates total AI-related federal spending.
  5. "generative AI" in a 10-K may include strategy mentions alongside
     confirmed deployments. Treat as a disclosure signal, not a confirmed
     deployment count.

Outputs to data/adoption.json.

Usage:
    pip install requests
    python scripts/fetch_adoption.py
"""

import json
import re
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
WINDOW_DAYS     = 365   # rolling 12-month window
REQUEST_TIMEOUT = 30    # seconds per HTTP request
MAX_EXAMPLES    = 10    # US federal contract examples to include

# Signal 1 — Government Procurement keyword sets
US_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "generative AI",
    "large language model",
    "AI system",
]
CN_KEYWORD_ZH = "人工智能"   # artificial intelligence

# Signal 2 — EDGAR disclosure term
# "generative AI" is specific to the post-2022 AI wave and broadly used in
# annual reports to indicate meaningful AI engagement. Avoids the overly narrow
# "AI deployment" exact phrase while remaining more specific than just "AI".
EDGAR_TERM = "generative AI"

# ── API endpoints ─────────────────────────────────────────────────────────────
USASPENDING_URL  = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
CCGP_SEARCH_URL  = "http://search.ccgp.gov.cn/bxsearch"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

US_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker/1.0 "
        "(public research; github.com/cohenis13/US-China-AI-Race)"
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
EDGAR_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker/1.0 "
        "(public research; github.com/cohenis13/US-China-AI-Race)"
    ),
    "Accept": "application/json",
}


# ── Date helpers ──────────────────────────────────────────────────────────────
def date_range() -> tuple[str, str]:
    """Return (start_date, end_date) for the rolling window (YYYY-MM-DD)."""
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=WINDOW_DAYS)
    return str(start), str(end)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 1a — US Government Procurement (USASpending.gov)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_us_procurement(start_date: str, end_date: str) -> dict:
    """
    Count US federal AI contract awards from USASpending.gov.

    - time_period filter applies to the action_date (transaction date),
      not the contract start date. This is why returned examples may show
      "Contract Start" dates outside the rolling window — those are the
      period_of_performance_start_date, which can predate the action.
    - Sort by Award Amount (desc) to surface the largest AI-related contracts.
    - Award types A–D = contracts only (excludes grants, loans, IDVs).

    Returns: count, examples, status, confidence
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
            "Start Date",           # period_of_performance_start_date (may predate window)
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

        results  = data.get("results", [])
        log.info(
            "US procurement: %d federal AI contract awards in window "
            "(sorted by award amount; contract start dates may predate window)",
            count,
        )

        examples = []
        for r in results[:MAX_EXAMPLES]:
            agency = r.get("Awarding Agency") or r.get("Awarding Sub Agency") or ""
            desc   = r.get("Description") or ""
            examples.append({
                "award_id":       r.get("Award ID", ""),
                "recipient":      r.get("Recipient Name", ""),
                "amount":         r.get("Award Amount"),
                # "Start Date" from USASpending = period_of_performance_start_date.
                # This is the contract start date, which may predate the rolling
                # window. The action_date (which triggered inclusion in the window)
                # is not returned by this endpoint.
                "contract_start": r.get("Start Date", ""),
                "agency":         agency,
                "description":    desc[:120] if desc else "",
                "country":        "US",
            })

        return {
            "count":      count,
            "examples":   examples,
            "status":     "ok",
            "confidence": "medium",
            "note": (
                "Federal contract awards (types A–D) with AI keywords in award descriptions. "
                "Action-date filter limits to the rolling window; contract start dates "
                "shown in examples may predate the window (multi-year contracts). "
                "Federal government only — excludes state, local, and private sector. "
                "Likely understates total federal AI spend (not all contracts use explicit AI keywords)."
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


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 1b — China Government Procurement (CCGP)
# ─────────────────────────────────────────────────────────────────────────────
def _parse_ccgp_total(html: str) -> int | None:
    """Extract result count from CCGP HTML. Tries patterns most- to least-specific."""
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

    CCGP date format: YYYY:MM:DD (colon-separated, not hyphen).
    Single keyword to avoid cross-term double-counting from HTML scraping.
    GitHub Actions (Azure US East IPs) are commonly blocked — status="blocked"
    when inaccessible. Blocked ≠ zero procurement.

    Returns: count (or None), status, confidence
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
                f"Response too short ({len(resp.content)} bytes) — likely blocked/redirect"
            )
        if "html" not in ct and "text" not in ct:
            raise ValueError(f"Unexpected content-type: {ct!r}")

        try:
            html = resp.content.decode("utf-8")
        except UnicodeDecodeError:
            html = resp.content.decode("gb18030", errors="replace")

        count = _parse_ccgp_total(html)

        if count is None:
            log.warning(
                "CCGP: result count not found in response HTML "
                "(len=%d, status=%d) — page structure may have changed",
                len(html), resp.status_code,
            )
            return {
                "count":      None,
                "status":     "partial",
                "confidence": "unavailable",
                "note": (
                    "CCGP returned a response but the total count could not be parsed. "
                    "Page structure may have changed. "
                    "Central-government only; sub-national procurement not captured."
                ),
            }

        log.info(
            "CN procurement: %d notices for '%s' in window",
            count, CN_KEYWORD_ZH,
        )
        return {
            "count":      count,
            "status":     "ok",
            "confidence": "low",
            "note": (
                f"Central-government procurement notices only (CCGP). "
                f"Keyword: '{CN_KEYWORD_ZH}' (artificial intelligence). "
                "Sub-national procurement not captured. "
                "Significant undercount of total government AI procurement expected."
            ),
        }

    except requests.exceptions.Timeout:
        log.warning("CCGP: timed out (likely blocked — Azure US East IPs)")
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
            "GitHub Actions runs on Azure US East IPs, which CCGP commonly blocks. "
            "null ≠ zero — China government AI procurement is ongoing; "
            "only the data pipeline is blocked."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 2 — Corporate Filing Disclosures (SEC EDGAR EFTS)
# ─────────────────────────────────────────────────────────────────────────────
def _edgar_count(params: dict, label: str, retries: int = 2) -> int | None:
    """
    Execute one EDGAR EFTS query and return the total hit count.

    Retries up to `retries` times with exponential backoff to handle
    transient rate-limits (GitHub Actions IPs may be throttled by SEC).
    Returns None on any error after all retries.
    """
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                delay = 2 ** attempt     # 2s, 4s backoff
                log.info("%s: retry %d/%d after %ds backoff …", label, attempt, retries, delay)
                time.sleep(delay)

            resp = requests.get(
                EDGAR_SEARCH_URL,
                params=params,
                headers=EDGAR_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            hits_block = data.get("hits", {})
            total      = hits_block.get("total")
            if isinstance(total, dict):
                count = int(total.get("value", 0))
            elif total is not None:
                count = int(total)
            else:
                log.warning(
                    "%s: unexpected EFTS response shape — keys: %s",
                    label, list(data.keys()),
                )
                return None

            log.info("%s: %d filings", label, count)
            return count

        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429 or resp.status_code == 403:
                log.warning("%s: HTTP %d (rate limit / access denied) — %s", label, resp.status_code, e)
                if attempt < retries:
                    continue   # will retry with backoff
            else:
                log.error("%s: HTTP error — %s", label, e)
            break

        except Exception as e:
            log.error("%s: EDGAR query failed — %s", label, e)
            break

    return None


def fetch_edgar(form_type: str, start_date: str, end_date: str) -> dict:
    """
    Count SEC EDGAR filings of a given form type that mention EDGAR_TERM
    within the rolling window, plus the total filers for context.

    form_type:
      "10-K"  — US domestic public companies (annual report)
      "20-F"  — Foreign private issuers; Chinese ADRs are the largest
                segment (~40% of 20-F filers by count) but not exclusive.

    Two queries:
      (a) With query term  → deployment-disclosure count
      (b) Without keyword  → total filers denominator
    Deployment rate = (a) / (b) — expressed as a percentage.

    Status:
      "ok"      — 10-K (US domestic companies)
      "partial"  — 20-F (proxy coverage; not exclusively China)
      "error"   — fetch failed
    """
    label     = f"EDGAR {form_type}"
    is_proxy  = (form_type == "20-F")
    base_date = {"forms": form_type, "dateRange": "custom", "startdt": start_date, "enddt": end_date}

    # (a) Filings mentioning the deployment term
    deploy_count = _edgar_count(
        {**base_date, "q": f'"{EDGAR_TERM}"'},
        f"{label} with '{EDGAR_TERM}'",
    )

    # (b) Total filings in the period (denominator) — use a term present in
    # virtually every annual report as a proxy for "all filers"
    total_filers = _edgar_count(
        {**base_date, "q": '"results of operations"'},
        f"{label} total filers proxy",
    )

    if deploy_count is None:
        return {
            "count":         None,
            "total_filers":  total_filers,
            "status":        "error",
            "confidence":    "low",
            "note":          "EDGAR query failed — see logs.",
        }

    deploy_rate = None
    if total_filers and total_filers > 0:
        deploy_rate = round(deploy_count / total_filers * 100, 1)

    log.info(
        "%s: %d of ~%d filers mention '%s' (%.1f%%)",
        label,
        deploy_count,
        total_filers or 0,
        EDGAR_TERM,
        deploy_rate or 0.0,
    )

    if is_proxy:
        note = (
            f"20-F filings cover all foreign private issuers listed on US exchanges. "
            f"Chinese ADRs are the largest segment (~40% of filers) but this is not "
            f"exclusively China — also includes European, Korean, and other issuers. "
            f"Counts {form_type} annual reports mentioning \"{EDGAR_TERM}\". "
            f"Treat as a directional proxy, not a China-specific count. "
            f"Deployment rate = filers mentioning term ÷ total 20-F filers in period."
        )
        status = "partial"
    else:
        note = (
            f"US domestic public company annual reports (10-K) mentioning "
            f"\"{EDGAR_TERM}\". "
            f"May include strategy/exploration mentions alongside confirmed deployments. "
            f"Counts filings (typically one per company per year). "
            f"Deployment rate = filers mentioning term ÷ total 10-K filers in period."
        )
        status = "ok"

    return {
        "count":         deploy_count,
        "total_filers":  total_filers,
        "deploy_rate_pct": deploy_rate,
        "status":        status,
        "confidence":    "low" if is_proxy else "medium",
        "note":          note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE SCORING
# ─────────────────────────────────────────────────────────────────────────────
def compute_composite(proc: dict, edgar: dict, label: str) -> dict:
    """
    Compute a transparent composite adoption proxy score (0–10).

    Components (each 0–5 points):
      Procurement: log-scaled count / baseline. Baseline chosen so that
        ~2,000 contracts (estimated US annual AI procurement on EDGAR-visible
        keywords) maps to ~5 points. For China, same scale if available.
      EDGAR rate: deployment_rate_pct / 20 * 5 (20% rate → 5 pts).

    Confidence:
      high   — both signals available
      medium — one signal available
      low    — no signals available or all blocked
    """
    import math

    components = []
    score      = 0.0

    # Procurement component (0–5 pts)
    if proc.get("status") in ("ok",) and proc.get("count") is not None:
        # log scale so score doesn't collapse for small counts
        # 1 contract → ~0.5; 100 → ~3; 2000 → ~5
        proc_pts = min(math.log10(max(proc["count"], 1) + 1) / math.log10(2001) * 5, 5.0)
        proc_pts = round(proc_pts, 2)
        score   += proc_pts
        components.append({
            "name":  "government_procurement",
            "score": proc_pts,
            "input": proc["count"],
            "note":  "log10-scaled; 2000 contracts ≈ 5 pts",
        })

    # EDGAR component (0–5 pts)
    rate = edgar.get("deploy_rate_pct")
    if edgar.get("status") in ("ok", "partial") and rate is not None:
        edgar_pts = min(rate / 20 * 5, 5.0)
        edgar_pts = round(edgar_pts, 2)
        score    += edgar_pts
        components.append({
            "name":  "company_filings",
            "score": edgar_pts,
            "input": rate,
            "note":  "deploy_rate_pct / 20 * 5; 20% → 5 pts",
        })

    # Confidence
    n_signals = len(components)
    if n_signals >= 2:
        confidence = "medium"     # both signals contribute
    elif n_signals == 1:
        confidence = "low"        # only one signal
    else:
        confidence = "no-data"

    return {
        "score":      round(score, 1),
        "confidence": confidence,
        "components": components,
        "note": (
            f"Transparent proxy score for {label} AI adoption visibility. "
            "Two-component: government procurement (log-scaled) + EDGAR disclosure rate. "
            "Score reflects observable public signals, not total adoption. "
            "Not directly comparable across countries due to coverage asymmetry."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SANITY CHECK
# ─────────────────────────────────────────────────────────────────────────────
def sanity_check(us_proc: dict, us_edgar: dict) -> None:
    """Abort if both primary US signals have errored out."""
    if us_proc["status"] == "error" and us_edgar["status"] == "error":
        log.error("FAIL: Both US signals returned errors — aborting")
        sys.exit(1)

    if us_proc["status"] == "ok" and (us_proc.get("count") or 0) == 0:
        log.error(
            "FAIL: US procurement count = 0 over %d days — "
            "keyword filter or API may be broken",
            WINDOW_DAYS,
        )
        sys.exit(1)

    log.info(
        "Sanity check OK — US procurement: %s (%s), US EDGAR: %s (%s)",
        us_proc.get("count"), us_proc["status"],
        us_edgar.get("count"), us_edgar["status"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    start_date, end_date = date_range()
    log.info("Window: %s → %s (%d days)", start_date, end_date, WINDOW_DAYS)

    log.info("Signal 1a — US procurement (USASpending.gov) …")
    us_proc  = fetch_us_procurement(start_date, end_date)

    log.info("Signal 1b — China procurement (CCGP) …")
    cn_proc  = fetch_cn_procurement(start_date, end_date)

    log.info('Signal 2a — US company filings (EDGAR 10-K, "%s") …', EDGAR_TERM)
    us_edgar = fetch_edgar("10-K", start_date, end_date)

    log.info('Signal 2b — China proxy filings (EDGAR 20-F, "%s") …', EDGAR_TERM)
    cn_edgar = fetch_edgar("20-F", start_date, end_date)

    sanity_check(us_proc, us_edgar)

    # Composite scores
    composite_us    = compute_composite(us_proc, us_edgar, "US")
    composite_china = compute_composite(cn_proc, cn_edgar, "China")

    now = datetime.now(timezone.utc).isoformat()

    output = {
        "dimension":    "adoption",
        "metric_key":   "ai_adoption_signals",
        "description": (
            "Two-signal proxy for observable AI deployment activity. "
            "Signal 1: government procurement orders (binding institutional decisions). "
            "Signal 2: corporate annual report disclosures of generative AI. "
            "Neither signal is a complete or symmetric measure of total adoption."
        ),
        "fetched_at":   now,
        "last_updated": now,           # alias for downstream compatibility
        "window_days":  WINDOW_DAYS,
        "start_date":   start_date,
        "end_date":     end_date,

        "signals": {
            "government_procurement": {
                "description": (
                    "Government AI procurement orders — contracts awarded or modified "
                    "within the rolling window. US: federal contracts with AI keywords. "
                    "China: central-government procurement notices (CCGP, best-effort). "
                    "Counts the action_date transaction, not contract start date."
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
                    "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                    "note":       us_proc.get("note", ""),
                },
                "China": {
                    "count":      cn_proc.get("count"),
                    "status":     cn_proc["status"],
                    "confidence": cn_proc["confidence"],
                    "source":     "CCGP (中国政府采购网)",
                    "source_url": "http://search.ccgp.gov.cn/bxsearch",
                    "note":       cn_proc.get("note", ""),
                },
            },

            "company_filings": {
                "description": (
                    f"Public company annual filings mentioning \"{EDGAR_TERM}\" "
                    "in SEC EDGAR full-text search. "
                    "US: 10-K domestic companies. "
                    "China proxy: 20-F foreign private issuers (primarily Chinese ADRs). "
                    "Deployment rate = matching filers ÷ total filers in period."
                ),
                "query_term":  EDGAR_TERM,
                "query_terms": [EDGAR_TERM],   # list for forward-compatibility
                "US": {
                    "count":            us_edgar.get("count"),
                    "total_filers":     us_edgar.get("total_filers"),
                    "deploy_rate_pct":  us_edgar.get("deploy_rate_pct"),
                    "status":           us_edgar["status"],
                    "confidence":       us_edgar["confidence"],
                    "source":           "SEC EDGAR (10-K filings)",
                    "source_url":       "https://efts.sec.gov/LATEST/search-index",
                    "note":             us_edgar.get("note", ""),
                },
                "China_proxy": {
                    "count":            cn_edgar.get("count"),
                    "total_filers":     cn_edgar.get("total_filers"),
                    "deploy_rate_pct":  cn_edgar.get("deploy_rate_pct"),
                    "status":           cn_edgar["status"],
                    "confidence":       cn_edgar["confidence"],
                    "source":           "SEC EDGAR (20-F filings)",
                    "source_url":       "https://efts.sec.gov/LATEST/search-index",
                    "note":             cn_edgar.get("note", ""),
                },
            },
        },

        # US federal contract examples — sorted by award amount (largest first).
        # "contract_start" = period_of_performance_start_date, which may predate
        # the search window. Contracts appear because a procurement action
        # (award or modification) occurred within the rolling window.
        "top_examples":    us_proc.get("examples", []),
        "examples_note": (
            "Examples sorted by award amount (largest first). "
            "'Contract Start' = period_of_performance_start_date, which may predate "
            "the rolling window. Contracts appear because a procurement action "
            "(award or modification) fell within the window."
        ),

        "sample_size":       len(us_proc.get("examples", [])),
        "issuers_scanned":   {
            "US":          us_edgar.get("total_filers"),
            "China_proxy": cn_edgar.get("total_filers"),
        },
        "filings_scanned":   {
            "US":          us_edgar.get("total_filers"),
            "China_proxy": cn_edgar.get("total_filers"),
        },

        "composite_us":    composite_us,
        "composite_china": composite_china,
        "confidence":      "medium" if us_proc["status"] == "ok" else "low",

        "source_urls": {
            "usaspending": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            "ccgp":        "http://www.ccgp.gov.cn",
            "edgar_efts":  "https://efts.sec.gov/LATEST/search-index",
        },

        "methodology_note": (
            "Adoption is a proxy for observable deployment, not total adoption. "
            "Procurement captures institutional purchase/rollout intent — "
            "a binding decision to acquire AI is stronger evidence than strategy mentions. "
            "Public company filings capture self-reported generative AI use in annual reports. "
            "Both signals are subject to reporting and accessibility asymmetries: "
            "US data is substantially more automatable than China data. "
            "The US/China ratio reflects this transparency gap, not necessarily a "
            "proportional difference in actual AI adoption rates. "
            "CCGP null = pipeline blocked (not zero procurement). "
            "20-F proxy covers all foreign-listed issuers, not China exclusively. "
            "Compare directionally only."
        ),

        "coverage_note": (
            "Coverage is asymmetric by design of public reporting systems, not by analysis choice. "
            "US: full federal procurement API + all SEC-registered public companies. "
            "China: central procurement portal only (often inaccessible remotely) + "
            "US-exchange-listed Chinese ADRs only (Alibaba, Baidu, JD, PDD, etc.). "
            "Chinese companies listed exclusively on domestic or HK exchanges are not captured. "
            "This is a known and documented limitation."
        ),

        "caveats": (
            "1. Scope asymmetry: US = federal + US-listed public companies; "
            "China = central CCGP notices (often blocked) + Chinese ADRs (non-exclusive). "
            "2. CCGP null = inaccessible from runner, not zero procurement. "
            "3. 20-F proxy includes non-Chinese foreign issuers. "
            "4. 'Generative AI' disclosures include strategy mentions alongside deployments. "
            "5. Contract start dates in examples may predate the rolling window. "
            "6. Composite scores are transparent proxies, not validated adoption indices."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("═══ Output: %s", OUTPUT_FILE)
    log.info("  Window: %s → %s", start_date, end_date)
    log.info("  Signal 1 — Government Procurement:")
    log.info("    US:   %6s  (status: %s)", us_proc.get("count"), us_proc["status"])
    log.info("    CN:   %6s  (status: %s)", cn_proc.get("count"), cn_proc["status"])
    log.info("  Signal 2 — EDGAR '%s' disclosures:", EDGAR_TERM)
    log.info(
        "    US 10-K:  %s of ~%s filers  (%.1f%%) (status: %s)",
        us_edgar.get("count"), us_edgar.get("total_filers"),
        us_edgar.get("deploy_rate_pct") or 0.0, us_edgar["status"],
    )
    log.info(
        "    20-F:     %s of ~%s filers  (%.1f%%) (status: %s)",
        cn_edgar.get("count"), cn_edgar.get("total_filers"),
        cn_edgar.get("deploy_rate_pct") or 0.0, cn_edgar["status"],
    )
    log.info("  Composite:  US=%.1f (%s)  China=%.1f (%s)",
             composite_us["score"],    composite_us["confidence"],
             composite_china["score"], composite_china["confidence"])


if __name__ == "__main__":
    main()
