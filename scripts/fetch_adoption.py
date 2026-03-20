#!/usr/bin/env python3
"""
Fetch AI Adoption proxy data — two-signal model (v4).

WHAT THIS MEASURES
  Observable AI deployment signals in public records.
  This is a proxy for visible adoption, NOT a total adoption census.

SIGNAL 1 — GOVERNMENT PROCUREMENT
  US:    USASpending.gov federal contract awards — keyword match in award descriptions.
         The time_period filter applies to the action_date (transaction date), so a
         multi-year contract originally signed years ago may appear if a new procurement
         action (modification, increment) fell within the window.
  China: CCGP (中国政府采购网) — HTML scraping, best-effort.
         GitHub Actions (Azure US East IPs) are frequently blocked.
         status="blocked" when inaccessible. null ≠ zero procurement.

SIGNAL 2 — PUBLIC COMPANY DEPLOYMENT DISCLOSURES
  US:    SEC EDGAR 10-K annual reports mentioning deployment-oriented AI language.
         Queries the EDGAR EFTS full-text search API with a representative set of
         deployment terms. Returns count + sample company names from results.
  China: SEC EDGAR 20-F annual reports from foreign private issuers.
         Chinese ADRs are the dominant segment (~40% of 20-F filers) but this is
         not exclusively Chinese companies.
         Coverage asymmetry: Tencent, ByteDance, Meituan etc. are not in EDGAR.

COVERAGE HONESTY
  Both signals are subject to structural transparency asymmetries:
  - US data is substantially more automatable.
  - China procurement data is frequently inaccessible from US-based runners.
  - Chinese company disclosures in EDGAR cover US-listed ADRs only.
  These asymmetries are documented in the output, not hidden.

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
WINDOW_DAYS        = 365   # rolling 12-month window
REQUEST_TIMEOUT    = 30    # seconds per HTTP request
MAX_EXAMPLES       = 10    # US procurement examples
EDGAR_SAMPLE_SIZE  = 20    # max entity names to extract from EDGAR results
EDGAR_RETRY_COUNT  = 2     # retries on 429/403
EDGAR_SLEEP_SECS   = 1.0   # pause between EDGAR API calls (SEC rate limit: 10 req/s)

# Signal 1 — Government Procurement
US_KEYWORDS   = [
    "artificial intelligence",
    "machine learning",
    "generative AI",
    "large language model",
    "AI system",
]
CN_KEYWORD_ZH = "人工智能"

# Signal 2 — Company Deployment Disclosures
# "generative AI" is the primary term: specific to the post-2022 AI wave,
# broadly used in annual reports to indicate meaningful AI engagement.
# We supplement with "large language model" as a second specific term.
EDGAR_TERMS = [
    "generative AI",
    "large language model",
]
# Primary term for headline count (to avoid double-counting from two queries).
# Secondary terms used for coverage notes.
EDGAR_PRIMARY_TERM = "generative AI"

# ── API endpoints ─────────────────────────────────────────────────────────────
USASPENDING_URL  = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
CCGP_SEARCH_URL  = "http://search.ccgp.gov.cn/bxsearch"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

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
# SEC explicitly requires a descriptive User-Agent with contact info.
EDGAR_HEADERS = {
    "User-Agent": (
        "us-china-ai-tracker (non-commercial public research; "
        "github.com/cohenis13/US-China-AI-Race)"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
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

    The time_period filter applies to action_date (the transaction date),
    not period_of_performance_start_date. Multi-year contracts can appear
    in this window even if they originated years ago, as long as a recent
    procurement action (modification, increment) fell within the window.
    This explains why 'Contract Start' dates in examples may predate the window.
    """
    payload = {
        "filters": {
            "keywords":         US_KEYWORDS,
            "time_period":      [{"start_date": start_date, "end_date": end_date}],
            "award_type_codes": ["A", "B", "C", "D"],   # contracts only
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Start Date",          # = period_of_performance_start_date
            "Awarding Agency",
            "Awarding Sub Agency",
            "Description",
        ],
        "page":  1,
        "limit": MAX_EXAMPLES,
        "sort":  "Award Amount",   # largest first (most notable)
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
                # "Start Date" = period_of_performance_start_date.
                # May predate the rolling window — see examples_note in output.
                "contract_start": r.get("Start Date", ""),
                "agency":         agency,
                "description":    desc[:100] if desc else "",
                "country":        "US",
            })

        log.info(
            "US procurement: %d federal AI contract awards "
            "(action_date within window; contract start dates may predate it)",
            count,
        )
        return {
            "count":      count,
            "examples":   examples,
            "status":     "ok",
            "confidence": "medium",
            "note": (
                "Federal contract awards (types A–D) with AI keywords in descriptions. "
                "Filtered by action_date (the transaction date) — contract start dates "
                "shown may predate the window for multi-year contracts. "
                "Federal only; excludes state, local, and private sector. "
                "Likely understates total AI spend: not all AI contracts use explicit keywords."
            ),
        }

    except Exception as e:
        log.error("US procurement fetch failed: %s", e)
        return {
            "count":    None,
            "examples": [],
            "status":   "error",
            "confidence": "low",
            "note":     f"Fetch failed: {e}",
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
    Single keyword avoids cross-term double-counting via HTML scraping.
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

        ct = resp.headers.get("content-type", "")
        if len(resp.content) < 500:
            raise ValueError(
                f"Response too short ({len(resp.content)} bytes) — likely blocked"
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
                "CCGP: count not found in response (len=%d, status=%d)",
                len(html), resp.status_code,
            )
            return {
                "count":      None,
                "status":     "partial",
                "confidence": "unavailable",
                "note": (
                    "CCGP returned a response but the total count could not be parsed. "
                    "Page structure may have changed. Central-government only."
                ),
            }

        log.info("CN procurement: %d notices for '%s'", count, CN_KEYWORD_ZH)
        return {
            "count":      count,
            "status":     "ok",
            "confidence": "low",
            "note": (
                f"Central-government procurement notices only (CCGP). "
                f"Keyword: '{CN_KEYWORD_ZH}'. Sub-national procurement not captured. "
                "Significant undercount of total government AI procurement expected."
            ),
        }

    except requests.exceptions.Timeout:
        log.warning("CCGP: timed out — likely blocked (Azure US East IPs)")
    except requests.exceptions.ConnectionError as e:
        log.warning("CCGP: connection error — %s", e)
    except Exception as e:
        log.warning("CCGP: %s", e)

    return {
        "count":      None,
        "status":     "blocked",
        "confidence": "unavailable",
        "note": (
            "CCGP inaccessible from automated runner. "
            "GitHub Actions runs on Azure US East IPs, commonly blocked by CCGP. "
            "null ≠ zero — China government AI procurement is ongoing; "
            "only the data pipeline is blocked."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 2 — Public Company Deployment Disclosures (SEC EDGAR EFTS)
# ─────────────────────────────────────────────────────────────────────────────
def _edgar_request(session: requests.Session, params: dict, label: str) -> dict | None:
    """
    Execute one EDGAR EFTS HTTP request with retry on 429/403.

    Returns the parsed JSON response dict, or None on failure.
    SEC rate limit: 10 requests/second per IP.
    Sleeps EDGAR_SLEEP_SECS before each call to stay well under limit.
    """
    time.sleep(EDGAR_SLEEP_SECS)   # conservative pacing

    for attempt in range(EDGAR_RETRY_COUNT + 1):
        try:
            if attempt > 0:
                backoff = 3 * (2 ** (attempt - 1))   # 3s, 6s
                log.info("%s: retry %d after %ds backoff …", label, attempt, backoff)
                time.sleep(backoff)

            resp = session.get(
                EDGAR_SEARCH_URL,
                params=params,
                headers=EDGAR_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code in (403, 429):
                log.warning(
                    "%s: HTTP %d from EDGAR — likely rate-limit/IP block",
                    label, resp.status_code,
                )
                if attempt < EDGAR_RETRY_COUNT:
                    continue
                return None   # all retries exhausted

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            log.error("%s: HTTP error — %s", label, e)
            break
        except Exception as e:
            log.error("%s: request failed — %s", label, e)
            break

    return None


def _parse_edgar_response(data: dict, label: str) -> tuple[int | None, list[str]]:
    """
    Extract (total_count, entity_name_list) from an EDGAR EFTS response.

    Returns (None, []) if the response shape is unexpected.
    Entity names are extracted from the hits array when present.
    """
    if data is None:
        return None, []

    hits_block = data.get("hits", {})
    total      = hits_block.get("total")

    if isinstance(total, dict):
        count = int(total.get("value", 0))
    elif total is not None:
        count = int(total)
    else:
        log.warning("%s: unexpected EFTS response shape — keys: %s", label, list(data.keys()))
        return None, []

    # Extract sample entity names from the hits array.
    # EDGAR EFTS returns individual filings; we deduplicate by entity_name.
    entities_seen = set()
    entity_names  = []
    for hit in hits_block.get("hits", []):
        src  = hit.get("_source", {})
        name = src.get("entity_name") or src.get("display_names", [{}])[0].get("name", "")
        name = name.strip()
        if name and name not in entities_seen:
            entities_seen.add(name)
            entity_names.append(name)
            if len(entity_names) >= EDGAR_SAMPLE_SIZE:
                break

    log.info("%s: %d filings; sample entities: %s", label, count, entity_names[:5] or "none")
    return count, entity_names


def fetch_edgar(form_type: str, start_date: str, end_date: str) -> dict:
    """
    Count SEC EDGAR filings mentioning deployment-oriented AI language.

    Primary term: EDGAR_PRIMARY_TERM (headline count).
    Denominator:  total filers using a term present in virtually every annual
                  report ("results of operations") — gives deployment rate %.

    form_type:
      "10-K" — US domestic public companies
      "20-F" — Foreign private issuers (Chinese ADRs dominant but not exclusive)

    Also returns:
      sample_entities — up to 20 company names from search results
      status:
        "ok"      — 10-K (US companies)
        "partial"  — 20-F (proxy coverage; not exclusively China)
        "blocked"  — EDGAR returned 403/429 on all retries
        "error"   — unexpected failure
    """
    label    = f"EDGAR {form_type}"
    is_proxy = (form_type == "20-F")
    base     = {
        "forms":     form_type,
        "dateRange": "custom",
        "startdt":   start_date,
        "enddt":     end_date,
    }

    session = requests.Session()

    # (a) Primary term query — headline count + sample entity names
    data_a = _edgar_request(
        session,
        {**base, "q": f'"{EDGAR_PRIMARY_TERM}"'},
        f"{label} '{EDGAR_PRIMARY_TERM}'",
    )

    if data_a is None:
        log.warning("%s: primary query failed (likely 403/429) — marking blocked", label)
        return {
            "count":           None,
            "total_filers":    None,
            "deploy_rate_pct": None,
            "sample_entities": [],
            "status":          "blocked",
            "confidence":      "unavailable",
            "note": (
                "EDGAR EFTS was inaccessible from the automated runner (HTTP 403/429). "
                "GitHub Actions IPs may be throttled by the SEC. null ≠ zero disclosures. "
                "Retry on next workflow run."
            ),
        }

    deploy_count, sample_entities = _parse_edgar_response(data_a, f"{label} primary")

    if deploy_count is None:
        return {
            "count":           None,
            "total_filers":    None,
            "deploy_rate_pct": None,
            "sample_entities": [],
            "status":          "error",
            "confidence":      "low",
            "note":            "EDGAR response shape unexpected — see logs.",
        }

    # (b) Denominator query — total filers (term in virtually every annual report)
    data_b = _edgar_request(
        session,
        {**base, "q": '"results of operations"'},
        f"{label} total-filers proxy",
    )
    total_filers, _ = _parse_edgar_response(data_b, f"{label} denominator")

    deploy_rate: float | None = None
    if total_filers and total_filers > 0:
        deploy_rate = round(deploy_count / total_filers * 100, 1)

    session.close()

    log.info(
        "%s: %d of ~%s filers mention '%s' (%.1f%%)",
        label,
        deploy_count,
        total_filers or "?",
        EDGAR_PRIMARY_TERM,
        deploy_rate or 0.0,
    )

    if is_proxy:
        note = (
            f"20-F annual reports mentioning \"{EDGAR_PRIMARY_TERM}\". "
            "Covers all foreign private issuers on US exchanges — "
            "Chinese ADRs (Alibaba, Baidu, JD, PDD…) are the dominant segment "
            "but this is not exclusively China. Tencent, ByteDance, Meituan "
            "(HK/private) are NOT covered. "
            "Treat as a directional China proxy, not a China-specific count. "
            "Deployment rate = matching filers ÷ total 20-F filers in period."
        )
        status = "partial"
    else:
        note = (
            f"US domestic 10-K annual reports mentioning \"{EDGAR_PRIMARY_TERM}\". "
            "May include strategy/exploration alongside confirmed deployments. "
            "Deployment rate = matching filers ÷ total 10-K filers in period."
        )
        status = "ok"

    return {
        "count":           deploy_count,
        "total_filers":    total_filers,
        "deploy_rate_pct": deploy_rate,
        "sample_entities": sample_entities,
        "issuers_scanned": total_filers,
        "filings_scanned": total_filers,
        "status":          status,
        "confidence":      "low" if is_proxy else "medium",
        "note":            note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE SCORING
# ─────────────────────────────────────────────────────────────────────────────
def compute_composite(proc: dict, edgar: dict, label: str) -> dict:
    """
    Transparent composite adoption proxy score (0–10).

    Two components, each 0–5 points:
    - Procurement: log10-scaled. 1 action→~0.5 pt; 100→~3; 2000→5.
    - EDGAR rate:  deploy_rate_pct / 20 × 5. 20% rate → 5 pts.

    Confidence:
      "medium"  — both signals available
      "low"     — one signal
      "no-data" — no signals

    Provisional = True if any signal is blocked, partial, or error.
    """
    import math

    components = []
    score      = 0.0
    provisional = False

    # Procurement component
    if proc.get("status") == "ok" and proc.get("count") is not None:
        pts   = min(math.log10(max(proc["count"], 1) + 1) / math.log10(2001) * 5, 5.0)
        pts   = round(pts, 2)
        score += pts
        components.append({
            "name":  "government_procurement",
            "score": pts,
            "input": proc["count"],
            "note":  "log10-scaled; 2000 actions ≈ 5 pts",
        })
    elif proc.get("status") in ("blocked", "partial", "error", "unavailable"):
        provisional = True

    # EDGAR component
    rate = edgar.get("deploy_rate_pct")
    if edgar.get("status") in ("ok", "partial") and rate is not None:
        pts   = min(rate / 20 * 5, 5.0)
        pts   = round(pts, 2)
        score += pts
        components.append({
            "name":  "company_disclosures",
            "score": pts,
            "input": rate,
            "note":  "deploy_rate_pct / 20 × 5; 20% → 5 pts",
        })
        if edgar.get("status") == "partial":
            provisional = True
    elif edgar.get("status") in ("blocked", "error", "unavailable"):
        provisional = True

    n = len(components)
    if n >= 2:
        confidence = "medium"
    elif n == 1:
        confidence = "low"
    else:
        confidence = "no-data"

    return {
        "score":       round(score, 1),
        "confidence":  confidence,
        "provisional": provisional,
        "components":  components,
        "note": (
            f"Transparent proxy score for {label} observable AI adoption. "
            "Components: procurement (log-scaled) + EDGAR disclosure rate. "
            "Not a validated index — compare directionally only."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SANITY CHECK
# ─────────────────────────────────────────────────────────────────────────────
def sanity_check(us_proc: dict, us_edgar: dict) -> None:
    """
    Abort only if both primary US signals fail completely.
    Partial / blocked signals are not abort conditions.
    """
    if us_proc["status"] == "error" and us_edgar["status"] in ("error", "blocked"):
        log.error("FAIL: Both US signals are in error/blocked state — aborting")
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

    log.info('Signal 2a — US disclosures (EDGAR 10-K, "%s") …', EDGAR_PRIMARY_TERM)
    us_edgar = fetch_edgar("10-K", start_date, end_date)

    log.info('Signal 2b — China proxy disclosures (EDGAR 20-F, "%s") …', EDGAR_PRIMARY_TERM)
    cn_edgar = fetch_edgar("20-F", start_date, end_date)

    sanity_check(us_proc, us_edgar)

    # Composite scores
    composite_us    = compute_composite(us_proc, us_edgar, "US")
    composite_china = compute_composite(cn_proc, cn_edgar, "China")

    # Overall provisional flag: True if any signal is not "ok"
    any_blocked = any(
        s in ("blocked", "partial", "error", "unavailable")
        for s in [
            us_proc["status"], cn_proc["status"],
            us_edgar["status"], cn_edgar["status"],
        ]
    )

    now = datetime.now(timezone.utc).isoformat()

    output = {
        "dimension":   "adoption",
        "metric_key":  "ai_adoption_signals",
        "description": (
            "Two-signal proxy for observable AI deployment in public records. "
            "Signal 1: government procurement orders. "
            "Signal 2: public company annual report disclosures. "
            "This is NOT a total adoption census — coverage is structurally asymmetric."
        ),
        "fetched_at":   now,
        "last_updated": now,
        "window_days":  WINDOW_DAYS,
        "start_date":   start_date,
        "end_date":     end_date,

        # Provisional: true until both signals are stable and symmetric.
        # score_updated: true only if composite scores are reliable enough to
        # update the scorecard (requires both signals to be "ok" or "partial").
        "provisional":    any_blocked,
        "score_updated":  (
            composite_us["confidence"] in ("medium", "low")
            and composite_china["confidence"] in ("medium", "low")
        ),

        "signals": {
            "government_procurement": {
                "description": (
                    "Government AI procurement orders — contracts awarded or modified "
                    "within the rolling window. "
                    "US: federal contracts with AI keywords (action_date filtered). "
                    "China: CCGP central-government notices (best-effort; often blocked)."
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

            "company_disclosures": {
                "description": (
                    f"Annual reports mentioning \"{EDGAR_PRIMARY_TERM}\" "
                    "in SEC EDGAR full-text search. "
                    "US: 10-K domestic companies. "
                    "China proxy: 20-F foreign private issuers (Chinese ADRs dominant). "
                    "Deployment rate = matching filers ÷ total filers in period."
                ),
                "query_term":  EDGAR_PRIMARY_TERM,
                "query_terms": EDGAR_TERMS,
                "US": {
                    "count":           us_edgar.get("count"),
                    "total_filers":    us_edgar.get("total_filers"),
                    "issuers_scanned": us_edgar.get("issuers_scanned"),
                    "filings_scanned": us_edgar.get("filings_scanned"),
                    "deploy_rate_pct": us_edgar.get("deploy_rate_pct"),
                    "sample_entities": us_edgar.get("sample_entities", []),
                    "status":          us_edgar["status"],
                    "confidence":      us_edgar["confidence"],
                    "source":          "SEC EDGAR (10-K filings)",
                    "source_url":      "https://efts.sec.gov/LATEST/search-index",
                    "note":            us_edgar.get("note", ""),
                },
                "China_proxy": {
                    "count":           cn_edgar.get("count"),
                    "total_filers":    cn_edgar.get("total_filers"),
                    "issuers_scanned": cn_edgar.get("issuers_scanned"),
                    "filings_scanned": cn_edgar.get("filings_scanned"),
                    "deploy_rate_pct": cn_edgar.get("deploy_rate_pct"),
                    "sample_entities": cn_edgar.get("sample_entities", []),
                    "status":          cn_edgar["status"],
                    "confidence":      cn_edgar["confidence"],
                    "source":          "SEC EDGAR (20-F filings)",
                    "source_url":      "https://efts.sec.gov/LATEST/search-index",
                    "note":            cn_edgar.get("note", ""),
                },
            },
        },

        "top_examples":   us_proc.get("examples", []),
        "examples_note": (
            "Examples sorted by award amount (largest first). "
            "'Contract Start' = period_of_performance_start_date — may predate the "
            "rolling window because a procurement action (modification/increment) "
            "occurred within the window for a multi-year contract."
        ),
        "sample_size":    len(us_proc.get("examples", [])),

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
            "Procurement captures binding institutional decisions to acquire AI. "
            "Company disclosures capture self-reported generative AI use in annual reports, "
            "which may include strategy/exploration alongside confirmed deployments. "
            "Both signals are subject to structural transparency asymmetries: "
            "US data is substantially more automatable. "
            "China procurement (CCGP) is frequently inaccessible from US runners. "
            "China corporate coverage (20-F) covers US-listed ADRs only — "
            "not Tencent, ByteDance, or Meituan. "
            "Compare directionally only."
        ),

        "coverage_note": (
            "Coverage asymmetry reflects the design of public reporting systems, "
            "not an analytical choice. "
            "US: full federal procurement API + all US SEC-registered companies. "
            "China: central procurement portal only (often inaccessible remotely) + "
            "US-exchange-listed Chinese ADRs only. "
            "This is documented, not hidden."
        ),

        "caveats": (
            "1. CCGP null = pipeline blocked, not zero procurement. "
            "2. 20-F proxy includes non-Chinese foreign issuers. "
            "3. Disclosure counts may include strategy mentions alongside deployments. "
            "4. Contract start dates in examples may predate the rolling window. "
            "5. Composite scores are transparent proxies, not validated indices. "
            "6. If provisional=true, do not use scores for direct US–China comparison."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("═══ Output: %s", OUTPUT_FILE)
    log.info("  Window: %s → %s", start_date, end_date)
    log.info("  Provisional: %s  |  score_updated: %s", output["provisional"], output["score_updated"])
    log.info("  Signal 1 — Government Procurement:")
    log.info("    US:        %6s  (status: %s)", us_proc.get("count"), us_proc["status"])
    log.info("    China:     %6s  (status: %s)", cn_proc.get("count"), cn_proc["status"])
    log.info("  Signal 2 — Company Disclosures (EDGAR '%s'):", EDGAR_PRIMARY_TERM)
    log.info(
        "    US 10-K:   %6s of ~%s  (%.1f%%)  (status: %s)",
        us_edgar.get("count"), us_edgar.get("total_filers"),
        us_edgar.get("deploy_rate_pct") or 0.0, us_edgar["status"],
    )
    log.info(
        "    20-F:      %6s of ~%s  (%.1f%%)  (status: %s)",
        cn_edgar.get("count"), cn_edgar.get("total_filers"),
        cn_edgar.get("deploy_rate_pct") or 0.0, cn_edgar["status"],
    )
    log.info("  Composite:  US=%.1f (%s, prov=%s)  China=%.1f (%s, prov=%s)",
             composite_us["score"],    composite_us["confidence"],    composite_us["provisional"],
             composite_china["score"], composite_china["confidence"], composite_china["provisional"])


if __name__ == "__main__":
    main()
