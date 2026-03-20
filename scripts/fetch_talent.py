#!/usr/bin/env python3
"""
Fetch AI research paper data from OpenAlex API.

Uses OpenAlex's group_by endpoint to count AI papers by country of institution
for the last 12 months. OpenAlex pre-computes institution affiliations for most
papers, so Unknown rates are far lower than approaches based on keyword matching
against raw arXiv metadata.

Two API calls are made per run:
  1. group_by(country_code) — full country breakdown + total count in one call
  2. recent papers         — 15 most recent papers for the dashboard table

No API key is required. We add an email to the User-Agent header to join
OpenAlex's "polite pool" (higher rate limits). Update MAILTO below if desired.

Outputs to data/talent.json.

Usage:
    pip install requests
    python scripts/fetch_talent.py

This script is designed to run locally or via GitHub Actions.
"""

import json
import sys
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required.")
    print("Install it with:  pip install requests")
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
OUTPUT_FILE = ROOT / "data" / "talent.json"

# ── Config ───────────────────────────────────────────────────────
WINDOW_DAYS     = 365
OPENALEX_BASE   = "https://api.openalex.org/works"
REQUEST_TIMEOUT = 30
RATE_LIMIT_SLEEP = 1.0   # be polite; OpenAlex asks for a pause between requests
MAX_AUTHORS_OUT  = 3
MAX_PAPERS_TABLE = 15

# OpenAlex concept IDs for AI/ML/NLP/CV
# These are stable identifiers in OpenAlex's concept taxonomy.
CONCEPTS = "C154945302|C119857082|C204321447|C31972630"
# C154945302 = Artificial Intelligence
# C119857082 = Machine Learning
# C204321447 = Natural Language Processing
# C31972630  = Computer Vision

# Email for OpenAlex polite pool — update to a real contact if desired.
# See: https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
MAILTO = "ai-tracker@github-actions"

# Country codes that count as "US" or "China" for the summary
US_CODE = "US"
CN_CODE = "CN"


# ── API helpers ───────────────────────────────────────────────────

def openalex_get(params: dict) -> dict | None:
    """Make a GET request to OpenAlex and return parsed JSON, or None on failure."""
    headers = {"User-Agent": f"ai-race-tracker/1.0 (mailto:{MAILTO})"}
    try:
        resp = requests.get(OPENALEX_BASE, params=params, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        log.warning("OpenAlex request failed: %s", e)
        return None


# ── Country breakdown ─────────────────────────────────────────────

def fetch_country_breakdown(filter_str: str) -> tuple[dict, int]:
    """
    Fetch paper counts grouped by institution country code.

    Returns:
      - breakdown: {country_code: count} (None key = no affiliation)
      - total_papers: total papers matching the filter (from meta.count)
    """
    params = {
        "filter":   filter_str,
        "group_by": "authorships.institutions.country_code",
        "per_page": 200,   # ~195 UN country codes; 200 covers all in one page
        "mailto":   MAILTO,
    }
    data = openalex_get(params)
    if data is None:
        return {}, 0

    total_papers = data.get("meta", {}).get("count", 0)
    breakdown: dict[str | None, int] = {}
    for group in data.get("group_by", []):
        raw_key = group.get("key")        # URL like "https://openalex.org/countries/US", or null
        count   = group.get("count", 0)
        # Extract ISO 2-letter code from the URL (e.g. ".../countries/US" → "US")
        if raw_key:
            key = raw_key.split("/")[-1]  # "US", "CN", "GB", etc.
        else:
            key = None                    # no institutional affiliation
        breakdown[key] = count

    log.info("  Total papers matching filter: %d", total_papers)
    log.info("  Country groups returned:      %d", len(breakdown))
    return breakdown, total_papers


# ── Recent papers ─────────────────────────────────────────────────

def derive_primary_country(countries: list[str]) -> str:
    """
    Derive a single primary-country label from a paper's full country list.

    Rules:
      - US only (possibly + Other)  → "US"
      - China only (possibly + Other) → "China"
      - Both US and China            → "Mixed"
      - Other countries only         → "Other"
      - No countries                 → "Unknown"
    """
    country_set = set(countries)
    has_us = US_CODE in country_set
    has_cn = CN_CODE in country_set

    if has_us and has_cn:
        return "Mixed"
    if has_us:
        return "US"
    if has_cn:
        return "China"
    if country_set:
        return "Other"
    return "Unknown"


def fetch_recent_papers(filter_str: str, n: int = MAX_PAPERS_TABLE) -> list[dict]:
    """Fetch n most recent AI papers with authorship details."""
    params = {
        "filter":   filter_str,
        "sort":     "publication_date:desc",
        "per_page": n,
        "select":   "id,title,publication_date,authorships",
        "mailto":   MAILTO,
    }
    data = openalex_get(params)
    if data is None:
        return []

    papers = []
    for p in data.get("results", []):
        # Extract author names and institution country codes
        authors  = []
        countries: list[str] = []
        for auth in p.get("authorships", []):
            name = (auth.get("author") or {}).get("display_name", "")
            if name:
                authors.append(name)
            for code in auth.get("countries", []):
                if code and code not in countries:
                    countries.append(code)

        papers.append({
            "id":              p.get("id", ""),
            "title":           p.get("title", "") or "",
            "authors":         authors[:MAX_AUTHORS_OUT],
            "countries":       countries,
            "primary_country": derive_primary_country(countries),
            "published":       p.get("publication_date", ""),
            "source":          "openalex",
        })

    return papers


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    today      = datetime.now(timezone.utc).date()
    cutoff     = today - timedelta(days=WINDOW_DAYS)
    cutoff_str = cutoff.isoformat()    # YYYY-MM-DD  (start of window)
    today_str  = today.isoformat()     # YYYY-MM-DD  (cap future-dated papers)

    filter_str = (
        f"concepts.id:{CONCEPTS},"
        f"from_publication_date:{cutoff_str},"
        f"to_publication_date:{today_str}"
    )

    log.info("Window: %s → %s (%d days)", cutoff_str, today_str, WINDOW_DAYS)
    log.info("Concepts: %s", CONCEPTS)

    # ── Call 1: country breakdown ────────────────────────────────
    log.info("Fetching country breakdown via group_by …")
    breakdown, total_papers = fetch_country_breakdown(filter_str)

    if not breakdown:
        log.error("group_by call returned no data — aborting")
        sys.exit(1)

    # Aggregate into US / China / Other / Unknown
    us_count      = breakdown.get(US_CODE, 0)
    china_count   = breakdown.get(CN_CODE, 0)
    unknown_count = breakdown.get(None, 0) + breakdown.get("", 0)  # no affiliation
    other_count   = sum(
        cnt for code, cnt in breakdown.items()
        if code not in (US_CODE, CN_CODE, None, "")
    )
    total_attributed = us_count + china_count + other_count
    # Note: total_attributed may exceed total_papers because multinational
    # papers are counted once per country they appear in.

    # Top 10 countries for the methodology section
    top_countries = sorted(
        [
            {"country_code": k, "count": v}
            for k, v in breakdown.items()
            if k and k not in ("",)
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    time.sleep(RATE_LIMIT_SLEEP)

    # ── Call 2: recent papers ────────────────────────────────────
    log.info("Fetching %d most recent papers for table …", MAX_PAPERS_TABLE)
    recent_papers = fetch_recent_papers(filter_str)
    log.info("  → %d papers retrieved", len(recent_papers))

    # ── Build output ─────────────────────────────────────────────
    output = {
        "dimension":   "talent",
        "metric_key":  "ai_papers_by_country_12m",
        "description": (
            f"AI-related research papers (Artificial Intelligence, Machine Learning, "
            f"NLP, Computer Vision concepts) published in the last {WINDOW_DAYS} days, "
            "counted by country of author institution. Source: OpenAlex. "
            "A proxy for research output, not a complete measure of talent or capability."
        ),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW_DAYS,
        "source": {
            "name": "OpenAlex API",
            "url":  OPENALEX_BASE,
            "note": (
                "group_by=authorships.institutions.country_code on AI/ML/NLP/CV concepts. "
                "Papers with authors from multiple countries are counted in each country. "
                "OpenAlex pre-computes institutional affiliations from publisher metadata."
            ),
        },
        "summary": {
            "US":               us_count,
            "China":            china_count,
            "Other":            other_count,
            "Unknown":          unknown_count,
            "total_papers":     total_papers,
            "total_attributed": total_attributed,
        },
        "top_countries": top_countries,
        "papers": recent_papers,
        "methodology_note": (
            "Paper counts are sourced from OpenAlex, which indexes most major academic "
            "publishers and preprint servers (including arXiv). Each paper is counted "
            "once for each country where at least one author has an identified institution. "
            "A paper with US and Chinese co-authors is counted in both US and China totals "
            "— the sum of country counts therefore exceeds the total paper count. "
            "Country classification relies on OpenAlex's institution-to-country mapping, "
            "which uses ISO 3166-1 alpha-2 country codes. "
            "Unknown = papers where no author has any identified institutional affiliation "
            "in OpenAlex. "
            "This metric measures output volume — it does not capture citation impact, "
            "researcher headcount, or research quality. "
            "Coverage may exclude some journals or publishers not indexed by OpenAlex. "
            "Chinese researchers may also publish to venues not well-indexed internationally."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info(
        "Summary: US=%d  China=%d  Other=%d  Unknown=%d  Total=%d  Attributed=%d",
        us_count, china_count, other_count, unknown_count,
        total_papers, total_attributed,
    )


if __name__ == "__main__":
    main()
