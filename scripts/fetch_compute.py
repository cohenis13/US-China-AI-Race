#!/usr/bin/env python3
"""
Fetch supercomputer data from the TOP500 list and aggregate by country.

Scrapes the TOP500 HTML list pages (server-rendered, no API key required).
Extracts system name, country, and Rmax HPL performance for all 500 systems,
then aggregates into US / China / Other / Unknown totals.

Key implementation notes:
  - Country is embedded inside the "System" <td> cell (not a separate column).
    The cell has <br>-separated lines: Name / Site / Manufacturer / Country / Year.
    We parse country as the line immediately before the 4-digit year.
  - The table reports Rmax in PFlop/s (not TFlop/s) on current editions.
    We detect the unit from the column header and store accordingly.
  - TOP500 shows 10 systems per page. 500 systems = 50 pages.
    We stop early if a page returns 0 new systems or returns duplicates
    of the first page (protection against pagination not working).

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
    print("Error: 'beautifulsoup4' required. Run: pip install beautifulsoup4")
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
MAX_PAGES        = 60    # safety ceiling; 50 pages × 10 systems = 500
TARGET_SYSTEMS   = 500
REQUEST_TIMEOUT  = 30
RATE_LIMIT_SLEEP = 1.2
MAX_SYSTEMS_OUT  = 20

HEADERS = {
    "User-Agent": "us-china-ai-tracker/1.0 (public research dashboard)"
}

# Exact TOP500 country name → summary bucket
COUNTRY_BUCKETS = {
    "United States": "US",
    "China":         "China",
}


# ── Helpers ───────────────────────────────────────────────────────

def classify_country(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "Unknown"
    return COUNTRY_BUCKETS.get(name, "Other")


def get_latest_list_url() -> str:
    """Return the URL of the most recent TOP500 list, or FALLBACK_LIST."""
    try:
        resp = requests.get(TOP500_LISTS_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        pattern = re.compile(r"/lists/top500/(\d{4})/(\d{2})/?$")
        candidates = []
        for a in soup.find_all("a", href=True):
            m = pattern.search(a["href"])
            if m:
                candidates.append((int(m.group(1)), int(m.group(2)),
                                   f"{TOP500_BASE}{m.group(0).rstrip('/')}/"))
        if candidates:
            candidates.sort(reverse=True)
            url = candidates[0][2]
            log.info("Latest list detected: %s", url)
            return url
    except Exception as e:
        log.warning("Could not detect latest list URL: %s", e)
    log.info("Using fallback list URL: %s", FALLBACK_LIST)
    return FALLBACK_LIST


# ── Country extraction from System cell ───────────────────────────

def extract_country_from_system_cell(td) -> str:
    """
    Extract the country from a TOP500 'System' table cell.

    The cell layout (separated by <br> tags) is:
        System Name
        Site / Location
        Manufacturer
        Country          ← we want this
        Year

    Strategy: replace <br> with newlines, split into lines, find the last
    4-digit year line, return the line immediately before it.
    """
    # Clone the cell to avoid mutating the parse tree
    cell_copy = BeautifulSoup(str(td), "html.parser").find()
    if cell_copy is None:
        return ""

    for br in cell_copy.find_all("br"):
        br.replace_with("\n")

    raw = cell_copy.get_text()
    lines = [l.strip() for l in raw.split("\n") if l.strip()]

    # Find the last line that looks like a 4-digit year (1990–2030)
    year_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if re.fullmatch(r"(19|20)\d{2}", lines[i]):
            year_idx = i
            break

    if year_idx is not None and year_idx > 0:
        return lines[year_idx - 1]

    # Fallback: last line that isn't a year
    for line in reversed(lines):
        if not re.fullmatch(r"(19|20)\d{2}", line):
            return line

    return ""


# ── Table column detection ────────────────────────────────────────

def find_columns(header_cells: list) -> dict:
    """
    Return a dict of semantic name → column index from header cells.
    Also returns 'rmax_unit': 'pflops' or 'tflops' (default tflops).
    """
    col: dict = {}
    rmax_unit = "tflops"  # conservative default
    for i, th in enumerate(header_cells):
        text = th.get_text(strip=True).lower()
        if "rank" in text and "rank" not in col:
            col["rank"] = i
        if ("system" in text or text == "name") and "system" not in col:
            col["system"] = i
        if "rmax" in text and "rmax" not in col:
            col["rmax"] = i
            if "pflop" in text:
                rmax_unit = "pflops"
            elif "tflop" in text:
                rmax_unit = "tflops"
    col["rmax_unit"] = rmax_unit
    return col


def parse_rmax(text: str) -> float:
    try:
        return float(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def to_pflops(value: float, unit: str) -> float:
    """Convert a raw Rmax value to PFlop/s based on detected unit."""
    if unit == "tflops":
        return round(value / 1000, 3)
    # Already in PFlop/s
    return round(value, 3)


# ── Page fetching ─────────────────────────────────────────────────

def fetch_page(list_url: str, page: int) -> tuple[list[dict], dict]:
    """
    Fetch one page of the TOP500 list.
    Returns (systems, col_info) where col_info contains unit metadata.
    """
    url = f"{list_url}?page={page}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning("Page %d fetch failed: %s", page, e)
        return [], {}

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("Page %d: no <table> found", page)
        return [], {}

    rows = table.find_all("tr")
    if len(rows) < 2:
        return [], {}

    header_cells = rows[0].find_all(["th", "td"])
    col = find_columns(header_cells)
    rmax_unit = col.pop("rmax_unit", "tflops")

    log.debug("Page %d — columns: %s  rmax_unit: %s", page, col, rmax_unit)

    systems = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # Rank
        rank = 0
        if "rank" in col:
            try:
                rank = int(cells[col["rank"]].get_text(strip=True).replace(",", ""))
            except (ValueError, IndexError):
                pass

        # System name + country (both from the System cell)
        name = ""
        country_raw = ""
        sys_idx = col.get("system", 1)
        if sys_idx < len(cells):
            td = cells[sys_idx]
            # Name: text of the first <a> tag inside the cell, or first line
            a_tag = td.find("a")
            if a_tag:
                name = a_tag.get_text(strip=True)
            # Country: from <br>-delimited structure
            country_raw = extract_country_from_system_cell(td)

        # Rmax
        rmax_raw = 0.0
        if "rmax" in col and col["rmax"] < len(cells):
            rmax_raw = parse_rmax(cells[col["rmax"]].get_text(strip=True))

        systems.append({
            "rank":        rank,
            "name":        name,
            "country_raw": country_raw,
            "country":     classify_country(country_raw),
            "rmax_pflops": to_pflops(rmax_raw, rmax_unit),
        })

    return systems, {"rmax_unit": rmax_unit}


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    list_url = get_latest_list_url()
    parts = list_url.rstrip("/").split("/")
    list_edition = f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else "unknown"
    log.info("List edition: %s", list_edition)

    all_systems: list[dict] = []
    first_page_ranks: set[int] = set()
    rmax_unit_detected = "tflops"

    for page in range(1, MAX_PAGES + 1):
        log.info("  Page %d …", page)
        systems, meta = fetch_page(list_url, page)

        if not systems:
            log.info("  Page %d returned no systems — stopping", page)
            break

        if meta.get("rmax_unit"):
            rmax_unit_detected = meta["rmax_unit"]

        page_ranks = {s["rank"] for s in systems}

        # Stop if this page's ranks are identical to page 1 (pagination not working)
        if page == 1:
            first_page_ranks = page_ranks
        elif page_ranks == first_page_ranks:
            log.warning("Page %d returned same systems as page 1 — pagination not supported, stopping", page)
            break

        all_systems.extend(systems)
        log.info("    → %d systems (total so far: %d)", len(systems), len(all_systems))

        if len(all_systems) >= TARGET_SYSTEMS:
            log.info("  Reached %d systems — done", len(all_systems))
            break

        time.sleep(RATE_LIMIT_SLEEP)

    if not all_systems:
        log.error("No systems fetched — aborting")
        sys.exit(1)

    log.info("Rmax unit detected: %s", rmax_unit_detected)
    log.info("Total systems: %d", len(all_systems))

    # Sample country distribution for debugging
    country_sample = {}
    for s in all_systems[:20]:
        c = s["country"]
        country_sample[c] = country_sample.get(c, 0) + 1
    log.info("Country sample (first 20): %s", country_sample)

    # ── Aggregate ────────────────────────────────────────────────
    buckets: dict[str, dict] = {
        "US":      {"systems": 0, "rmax_pflops": 0.0},
        "China":   {"systems": 0, "rmax_pflops": 0.0},
        "Other":   {"systems": 0, "rmax_pflops": 0.0},
        "Unknown": {"systems": 0, "rmax_pflops": 0.0},
    }
    for s in all_systems:
        b = s["country"]
        buckets[b]["systems"]     += 1
        buckets[b]["rmax_pflops"] = round(buckets[b]["rmax_pflops"] + s["rmax_pflops"], 3)

    summary = {k: {"systems": v["systems"], "rmax_pflops": round(v["rmax_pflops"], 1)}
               for k, v in buckets.items()}

    top_systems = [
        {"rank": s["rank"], "name": s["name"],
         "country": s["country"], "rmax_pflops": s["rmax_pflops"]}
        for s in sorted(all_systems, key=lambda x: x["rank"])[:MAX_SYSTEMS_OUT]
    ]

    us    = summary["US"]
    china = summary["China"]

    output = {
        "dimension":    "compute",
        "metric_key":   "top500_compute_capacity",
        "description": (
            "Aggregate HPL benchmark performance (Rmax, PFlop/s) and system count "
            "from the TOP500 supercomputer list, grouped by country. "
            "A proxy for national high-end compute capacity. "
            "Does not capture private AI clusters or non-TOP500 systems."
        ),
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "list_edition": list_edition,
        "rmax_unit":    "PFlop/s",
        "source": {
            "name": "TOP500",
            "url":  "https://www.top500.org",
            "note": (
                f"HPL Rmax in PFlop/s (raw unit from table: {rmax_unit_detected}). "
                "List updated twice yearly (June and November). "
                "Country parsed from system cell metadata."
            ),
        },
        "summary": summary,
        "top_systems": top_systems,
        "methodology_note": (
            "Aggregate HPL Rmax performance is the primary metric — it weights systems "
            "by benchmark performance, capturing total capacity rather than just headcount. "
            "System count is secondary. Both are from the TOP500 list, which ranks the 500 "
            "most powerful non-distributed systems globally. "
            "Excludes private AI clusters, cloud GPU farms, and systems below TOP500 threshold. "
            "China has not submitted known exascale systems to TOP500 since 2021; "
            "its disclosed capacity is a significant undercount of actual capacity."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    for bucket, data in summary.items():
        log.info("  %-8s  %3d systems  %8.1f PFlop/s", bucket, data["systems"], data["rmax_pflops"])
    log.info("  US vs China: %.1f vs %.1f PFlop/s  (%d vs %d systems)",
             us["rmax_pflops"], china["rmax_pflops"], us["systems"], china["systems"])


if __name__ == "__main__":
    main()
