#!/usr/bin/env python3
"""
Fetch supercomputer data from the TOP500 list and aggregate by country.

Scrapes the TOP500 HTML list pages (server-rendered, no API key required).
Extracts system name, country, and Rmax HPL performance (TFlop/s) for all
500 systems across 10 paginated pages, then aggregates into US / China /
Other / Unknown totals.

Two metrics are produced:
  - Aggregate HPL Rmax performance (PFlop/s) — PRIMARY
  - System count per country — SECONDARY

Outputs to data/compute.json.

Usage:
    pip install requests beautifulsoup4
    python scripts/fetch_compute.py
"""

import json
import re
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Run: pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: 'beautifulsoup4' package is required. Run: pip install beautifulsoup4")
    sys.exit(1)

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "data" / "compute.json"

# ── Config ───────────────────────────────────────────────────────
TOP500_BASE      = "https://www.top500.org"
TOP500_LISTS_URL = f"{TOP500_BASE}/lists/top500/"
FALLBACK_LIST    = f"{TOP500_BASE}/lists/top500/2025/11/"
SYSTEMS_PER_PAGE = 50
TOTAL_PAGES      = 10   # 10 pages × 50 systems = 500
REQUEST_TIMEOUT  = 30
RATE_LIMIT_SLEEP = 1.5
MAX_SYSTEMS_OUT  = 20   # top systems to include in the JSON detail array

HEADERS = {
    "User-Agent": "us-china-ai-tracker/1.0 (research dashboard; public data)"
}

# Exact TOP500 country name → summary bucket
# All other non-empty values → "Other"
COUNTRY_BUCKETS = {
    "United States": "US",
    "China":         "China",
}


# ── Helpers ───────────────────────────────────────────────────────

def classify_country(country_name: str) -> str:
    """Map a TOP500 country name to US / China / Other / Unknown."""
    name = (country_name or "").strip()
    if not name:
        return "Unknown"
    return COUNTRY_BUCKETS.get(name, "Other")


def parse_rmax(text: str) -> float:
    """Parse a Rmax cell value to a float. Returns 0.0 on failure."""
    try:
        return float(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def to_pflops(tflops: float) -> float:
    """Convert TFlop/s to PFlop/s, rounded to 2 decimal places."""
    return round(tflops / 1000, 2)


# ── List URL detection ────────────────────────────────────────────

def get_latest_list_url() -> str:
    """
    Fetch the TOP500 lists index and return the URL of the most recent list.
    Falls back to FALLBACK_LIST if detection fails.
    """
    try:
        resp = requests.get(TOP500_LISTS_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        pattern = re.compile(r"/lists/top500/(\d{4})/(\d{2})/?$")
        candidates = []
        for a in soup.find_all("a", href=True):
            m = pattern.search(a["href"])
            if m:
                year, month = int(m.group(1)), int(m.group(2))
                full_url = f"{TOP500_BASE}{m.group(0).rstrip('/')}/"
                candidates.append((year, month, full_url))
        if candidates:
            candidates.sort(reverse=True)
            url = candidates[0][2]
            log.info("Latest list detected: %s", url)
            return url
    except Exception as e:
        log.warning("Could not detect latest list URL: %s", e)
    log.info("Using fallback list URL: %s", FALLBACK_LIST)
    return FALLBACK_LIST


# ── HTML table parsing ────────────────────────────────────────────

def find_column_indices(header_cells: list) -> dict:
    """
    Given header cells (list of BeautifulSoup elements), return a dict
    mapping semantic names to column indices. Values may be None if not found.
    """
    col: dict = {}
    for i, th in enumerate(header_cells):
        text = th.get_text(strip=True).lower()
        if "rank" in text and "rank" not in col:
            col["rank"] = i
        if ("system" in text or text == "name") and "name" not in col:
            col["name"] = i
        if "country" in text and "country" not in col:
            col["country"] = i
        if "rmax" in text and "rmax" not in col:
            col["rmax"] = i
        if "site" in text and "site" not in col:
            col["site"] = i
    return col


def fetch_page(list_url: str, page: int) -> list[dict]:
    """
    Fetch one paginated page of the TOP500 list.
    Returns a list of system dicts: {rank, name, country_raw, country, rmax_tflops}.
    """
    url = f"{list_url}?page={page}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning("Page %d fetch failed: %s", page, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("Page %d: no <table> element found in HTML", page)
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        log.warning("Page %d: table has fewer than 2 rows", page)
        return []

    # Detect column layout from header row
    header_cells = rows[0].find_all(["th", "td"])
    col = find_column_indices(header_cells)

    if "rmax" not in col:
        log.warning("Page %d: could not locate Rmax column in headers: %s",
                    page, [c.get_text(strip=True) for c in header_cells])

    systems = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        # Rank
        try:
            rank = int(cells[col.get("rank", 0)].get_text(strip=True).replace(",", ""))
        except (ValueError, IndexError, KeyError):
            rank = 0

        # System name (first 10 tokens to keep it concise)
        name_idx = col.get("name", 1)
        try:
            raw_name = cells[name_idx].get_text(separator=" ", strip=True)
            name = " ".join(raw_name.split()[:10])
        except (IndexError, KeyError):
            name = ""

        # Country — prefer dedicated Country column; fall back to last segment of Site cell
        country_raw = ""
        if "country" in col:
            try:
                country_raw = cells[col["country"]].get_text(strip=True)
            except IndexError:
                pass
        if not country_raw and "site" in col:
            try:
                site_text = cells[col["site"]].get_text(strip=True)
                parts = [p.strip() for p in site_text.split(",")]
                country_raw = parts[-1] if parts else ""
            except IndexError:
                pass

        # Rmax (TFlop/s)
        rmax = 0.0
        if "rmax" in col:
            try:
                rmax = parse_rmax(cells[col["rmax"]].get_text(strip=True))
            except IndexError:
                pass

        systems.append({
            "rank":        rank,
            "name":        name,
            "country_raw": country_raw,
            "country":     classify_country(country_raw),
            "rmax_tflops": rmax,
        })

    return systems


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    list_url = get_latest_list_url()

    # Extract edition label (e.g. "2025/11") from URL for the JSON
    parts = list_url.rstrip("/").split("/")
    list_edition = f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else "unknown"

    log.info("Fetching TOP500 list edition: %s", list_edition)

    all_systems: list[dict] = []
    for page in range(1, TOTAL_PAGES + 1):
        log.info("  Page %d/%d …", page, TOTAL_PAGES)
        systems = fetch_page(list_url, page)
        log.info("    → %d systems parsed", len(systems))
        all_systems.extend(systems)
        if page < TOTAL_PAGES:
            time.sleep(RATE_LIMIT_SLEEP)

    if not all_systems:
        log.error("No systems fetched — aborting")
        sys.exit(1)

    log.info("Total systems fetched: %d", len(all_systems))

    # ── Aggregate ────────────────────────────────────────────────
    buckets: dict[str, dict] = {
        "US":      {"systems": 0, "rmax_tflops": 0.0},
        "China":   {"systems": 0, "rmax_tflops": 0.0},
        "Other":   {"systems": 0, "rmax_tflops": 0.0},
        "Unknown": {"systems": 0, "rmax_tflops": 0.0},
    }
    for s in all_systems:
        b = s["country"]
        buckets[b]["systems"]     += 1
        buckets[b]["rmax_tflops"] += s["rmax_tflops"]

    summary = {
        bucket: {
            "systems":     data["systems"],
            "rmax_pflops": to_pflops(data["rmax_tflops"]),
        }
        for bucket, data in buckets.items()
    }

    # Top systems for the dashboard detail table
    top_systems = [
        {
            "rank":        s["rank"],
            "name":        s["name"],
            "country":     s["country"],
            "rmax_pflops": to_pflops(s["rmax_tflops"]),
        }
        for s in sorted(all_systems, key=lambda x: x["rank"])[:MAX_SYSTEMS_OUT]
    ]

    us    = summary["US"]
    china = summary["China"]

    output = {
        "dimension":    "compute",
        "metric_key":   "top500_compute_capacity",
        "description": (
            "Aggregate HPL benchmark performance (Rmax, in PFlop/s) and system count "
            "from the TOP500 supercomputer list, grouped by country. "
            "A proxy for national high-end compute capacity. "
            "Does not capture private AI clusters or non-TOP500 systems."
        ),
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "list_edition": list_edition,
        "source": {
            "name": "TOP500",
            "url":  "https://www.top500.org",
            "note": (
                "HPL (High Performance Linpack) Rmax benchmark in PFlop/s. "
                "List updated twice yearly (June and November). "
                "Country as reported by TOP500."
            ),
        },
        "summary": summary,
        "top_systems": top_systems,
        "methodology_note": (
            "Aggregate HPL Rmax performance is the primary metric — it weights systems by "
            "size, capturing total compute capacity rather than just headcount. "
            "System count is a secondary supporting metric. "
            "Both are sourced from the TOP500 list, which ranks the 500 most powerful "
            "non-distributed computer systems globally using the HPL benchmark. "
            "This metric excludes private AI training clusters not submitted to TOP500, "
            "systems below the TOP500 threshold, and cloud AI accelerator capacity. "
            "It is a proxy for disclosed high-end compute infrastructure, "
            "not a direct measure of AI training capacity."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("%-8s  %3s systems  %10.1f PFlop/s", "US",      us["systems"],    us["rmax_pflops"])
    log.info("%-8s  %3s systems  %10.1f PFlop/s", "China",   china["systems"], china["rmax_pflops"])
    log.info("%-8s  %3s systems  %10.1f PFlop/s", "Other",   summary["Other"]["systems"],   summary["Other"]["rmax_pflops"])
    log.info("%-8s  %3s systems  %10.1f PFlop/s", "Unknown", summary["Unknown"]["systems"], summary["Unknown"]["rmax_pflops"])


if __name__ == "__main__":
    main()
