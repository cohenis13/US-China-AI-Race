#!/usr/bin/env python3
"""
Fetch the full TOP500 supercomputer list and aggregate by country.

Data source:
  TOP500 publishes a downloadable XML file for each edition at:
    https://www.top500.org/lists/top500/YYYY/MM/download/TOP500_YYYYMM_all.xml

  The XML contains all 500 systems with dedicated <top500:rank>,
  <top500:system-name>, <top500:country>, and <top500:r-max> elements.
  Rmax is stored in GFlop/s; we convert to PFlop/s (÷ 1,000,000).

  No API key or authentication required for the download.

Two metrics are produced:
  - Aggregate HPL Rmax performance (PFlop/s) — PRIMARY
  - System count per country             — SECONDARY

Outputs to data/compute.json.

Usage:
    pip install requests
    python scripts/fetch_compute.py
"""

import io
import json
import re
import sys
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Run: pip install requests")
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
FALLBACK_YEAR    = 2025
FALLBACK_MONTH   = 11
REQUEST_TIMEOUT  = 60       # XML file is ~600 KB
MAX_SYSTEMS_OUT  = 20

HEADERS = {
    "User-Agent": "us-china-ai-tracker/1.0 (public research dashboard)",
    "Accept":     "application/xml,text/xml,*/*",
}

# Exact TOP500 country name → summary bucket
COUNTRY_BUCKETS = {
    "United States": "US",
    "China":         "China",
}

# Sanity thresholds
MIN_SYSTEMS_EXPECTED = 400   # warn if fewer than this parsed


# ── Country classification ────────────────────────────────────────

def classify_country(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "Unknown"
    return COUNTRY_BUCKETS.get(name, "Other")


# ── List edition detection ────────────────────────────────────────

def get_latest_edition() -> tuple[int, int]:
    """
    Fetch the TOP500 lists index and return (year, month) of the most
    recent edition. Falls back to FALLBACK_YEAR/FALLBACK_MONTH.
    """
    try:
        resp = requests.get(TOP500_LISTS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        pattern = re.compile(r"/lists/top500/(\d{4})/(\d{2})/?")
        candidates = []
        for m in pattern.finditer(resp.text):
            candidates.append((int(m.group(1)), int(m.group(2))))
        if candidates:
            candidates.sort(reverse=True)
            year, month = candidates[0]
            log.info("Latest edition detected: %d/%02d", year, month)
            return year, month
    except Exception as e:
        log.warning("Edition detection failed: %s", e)
    log.info("Using fallback edition: %d/%02d", FALLBACK_YEAR, FALLBACK_MONTH)
    return FALLBACK_YEAR, FALLBACK_MONTH


# ── XML download ──────────────────────────────────────────────────

def download_xml(year: int, month: int) -> bytes | None:
    """
    Download the full TOP500 XML file for the given edition.
    Returns raw bytes on success, None on failure.
    """
    ym  = f"{year:04d}{month:02d}"
    url = f"{TOP500_BASE}/lists/top500/{year:04d}/{month:02d}/download/TOP500_{ym}_all.xml"
    log.info("Downloading XML: %s", url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "html" in ct:
            log.error("Server returned HTML instead of XML — download may require auth")
            return None
        data = resp.content
        log.info("Downloaded %d bytes", len(data))
        return data
    except requests.exceptions.RequestException as e:
        log.error("XML download failed: %s", e)
        return None


# ── XML parsing ───────────────────────────────────────────────────

def strip_namespaces(root: ET.Element) -> ET.Element:
    """Remove XML namespace URI prefixes from all element tags in-place."""
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
    return root


def parse_xml(content: bytes) -> list[dict]:
    """
    Parse the TOP500 XML content and return a list of system dicts.

    XML structure (after namespace stripping):
      <list>
        <entry>  or  <system>
          <rank>1</rank>
          <system-name>El Capitan</system-name>
          <country>United States</country>
          <r-max>1809000000.0</r-max>   <!-- GFlop/s -->
          ...
        </entry>
        ...
      </list>

    Rmax is in GFlop/s. Convert to PFlop/s by dividing by 1,000,000.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        log.error("XML parse error: %s", e)
        return []

    strip_namespaces(root)

    # Collect all elements that contain a <rank> child — these are system entries
    systems = []

    def iter_system_elements(parent: ET.Element, depth: int = 0):
        """Recursively find system-level elements (those with a rank child)."""
        for child in parent:
            if child.find("rank") is not None:
                yield child
            elif depth < 2:
                yield from iter_system_elements(child, depth + 1)

    def txt(elem: ET.Element, *tags: str) -> str:
        """Return stripped text of the first matching child tag."""
        for tag in tags:
            sub = elem.find(tag)
            if sub is not None and sub.text:
                return sub.text.strip()
        return ""

    for entry in iter_system_elements(root):
        rank_str  = txt(entry, "rank")
        name      = txt(entry, "system-name", "systemname", "name", "description")
        country   = txt(entry, "country")
        rmax_str  = txt(entry, "r-max", "rmax", "rmax-gf", "rmax-tf")

        try:
            rank = int(rank_str)
        except ValueError:
            continue   # skip entries without a valid rank

        try:
            rmax_gflops = float(rmax_str.replace(",", ""))
            # GFlop/s → PFlop/s (÷ 1,000,000)
            rmax_pflops = round(rmax_gflops / 1_000_000, 2)
        except (ValueError, AttributeError):
            rmax_pflops = 0.0

        systems.append({
            "rank":        rank,
            "name":        name,
            "country_raw": country,
            "country":     classify_country(country),
            "rmax_pflops": rmax_pflops,
        })

    return sorted(systems, key=lambda x: x["rank"])


# ── Sanity checks ─────────────────────────────────────────────────

def sanity_check(systems: list[dict], edition_str: str) -> None:
    """
    Validate the parsed system list. Logs warnings for suspicious results
    and exits with code 1 if the data is clearly broken.
    """
    total = len(systems)
    us_count    = sum(1 for s in systems if s["country"] == "US")
    china_count = sum(1 for s in systems if s["country"] == "China")
    unk_count   = sum(1 for s in systems if s["country"] == "Unknown")

    log.info("Sanity check: %d systems, US=%d, China=%d, Unknown=%d",
             total, us_count, china_count, unk_count)

    if total == 0:
        log.error("FAIL: 0 systems parsed — aborting")
        sys.exit(1)

    if total < MIN_SYSTEMS_EXPECTED:
        log.warning("Only %d systems parsed (expected ~500) — data may be incomplete", total)

    if us_count == 0 and china_count == 0 and total > 50:
        log.error("FAIL: US=0 and China=0 with %d systems — country parsing is broken", total)
        sys.exit(1)

    if unk_count == total:
        log.error("FAIL: All %d systems are Unknown — country field not parsed", total)
        sys.exit(1)

    if us_count == 0:
        log.warning("US = 0 systems — unexpected for a TOP500 snapshot")
    if china_count == 0:
        log.warning("China = 0 systems — may reflect TOP500 submission gap (China stopped submitting exascale systems ~2021)")


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    year, month = get_latest_edition()
    edition_str = f"{year:04d}/{month:02d}"

    content = download_xml(year, month)
    if content is None:
        log.error("Could not download XML for edition %s — aborting", edition_str)
        sys.exit(1)

    log.info("Parsing XML …")
    systems = parse_xml(content)
    log.info("Parsed %d systems", len(systems))

    sanity_check(systems, edition_str)

    # ── Aggregate ────────────────────────────────────────────────
    buckets: dict[str, dict] = {
        "US":      {"systems": 0, "rmax_pflops": 0.0},
        "China":   {"systems": 0, "rmax_pflops": 0.0},
        "Other":   {"systems": 0, "rmax_pflops": 0.0},
        "Unknown": {"systems": 0, "rmax_pflops": 0.0},
    }
    for s in systems:
        b = s["country"]
        buckets[b]["systems"]     += 1
        buckets[b]["rmax_pflops"] = round(buckets[b]["rmax_pflops"] + s["rmax_pflops"], 2)

    summary = {
        k: {"systems": v["systems"], "rmax_pflops": round(v["rmax_pflops"], 1)}
        for k, v in buckets.items()
    }

    top_systems = [
        {
            "rank":        s["rank"],
            "name":        s["name"],
            "country":     s["country"],
            "rmax_pflops": s["rmax_pflops"],
        }
        for s in systems[:MAX_SYSTEMS_OUT]
    ]

    us    = summary["US"]
    china = summary["China"]
    total_parsed = len(systems)

    output = {
        "dimension":    "compute",
        "metric_key":   "top500_compute_capacity",
        "description": (
            "Aggregate HPL benchmark performance (Rmax, PFlop/s) and system count "
            "from the full TOP500 supercomputer list, grouped by country. "
            "A proxy for national high-end compute capacity. "
            "Does not capture private AI clusters or non-TOP500 systems."
        ),
        "fetched_at":          datetime.now(timezone.utc).isoformat(),
        "list_edition":        edition_str,
        "total_systems_parsed": total_parsed,
        "is_complete":         total_parsed >= MIN_SYSTEMS_EXPECTED,
        "source": {
            "name": "TOP500",
            "url":  "https://www.top500.org",
            "xml_download": (
                f"{TOP500_BASE}/lists/top500/{year:04d}/{month:02d}/download/"
                f"TOP500_{year:04d}{month:02d}_all.xml"
            ),
            "note": (
                "Full TOP500 XML download. Rmax in GFlop/s in source; stored as PFlop/s. "
                "List updated twice yearly (June and November). "
                "Country as reported by TOP500 submitters."
            ),
        },
        "summary": summary,
        "top_systems": top_systems,
        "methodology_note": (
            "Aggregate HPL Rmax performance is the primary metric — it weights systems "
            "by benchmark score, capturing total capacity not just headcount. "
            "System count is a secondary supporting metric. "
            "Source is the full TOP500 XML download (all 500 systems). "
            "Country is as reported by the submitting institution to TOP500. "
            "Excludes private AI clusters, cloud GPU farms, and any systems not submitted. "
            "China stopped submitting known exascale-class systems to TOP500 after 2021; "
            "its disclosed capacity is a significant undercount of actual capacity."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output: %s", OUTPUT_FILE)
    log.info("Edition: %s  |  Systems parsed: %d  |  Complete: %s",
             edition_str, total_parsed, output["is_complete"])
    for bucket, data in summary.items():
        log.info("  %-8s  %3d systems  %8.1f PFlop/s", bucket, data["systems"], data["rmax_pflops"])
    log.info("  US vs China: %.1f vs %.1f PFlop/s  (%d vs %d systems)",
             us["rmax_pflops"], china["rmax_pflops"], us["systems"], china["systems"])


if __name__ == "__main__":
    main()
