#!/usr/bin/env python3
"""
Fetch AI research paper data from arXiv API.

Classifies papers by country using keyword matching against:
  1. Author affiliation fields (when provided by arXiv — sparse)
  2. Abstract text (fallback — more common but noisier)

Institution keywords are maintained in data/institutions.json.

Outputs cleaned, timestamped data to data/talent.json.

Usage:
    pip install requests
    python scripts/fetch_talent.py

This script is designed to run locally or via GitHub Actions.

IMPORTANT NOTE ON COVERAGE:
arXiv does not expose a bulk download API for date-filtered results beyond
2000 records per query. For large categories like cs.LG and cs.CV (which
receive thousands of submissions per month), this script samples the most
recent 2000 papers rather than covering the full 12-month window. The
methodology_note in the output JSON documents this limitation explicitly.
"""

import json
import re
import sys
import time
import logging
import xml.etree.ElementTree as ET
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
ROOT              = Path(__file__).resolve().parent.parent
INSTITUTIONS_FILE = ROOT / "data" / "institutions.json"
OUTPUT_FILE       = ROOT / "data" / "talent.json"

# ── Config ───────────────────────────────────────────────────────
WINDOW_DAYS      = 365           # Filter cutoff: only keep papers newer than this
ARXIV_API_BASE   = "http://export.arxiv.org/api/query"
REQUEST_TIMEOUT  = 60            # seconds — arXiv can be slow for large result sets
RATE_LIMIT_SLEEP = 3.0           # arXiv requests: wait 3s between calls (their guideline)
RESULTS_PER_CAT  = 2000          # max papers per category (arXiv API upper bound)
MAX_AUTHORS_OUT  = 5             # cap author list in output JSON to keep file size down

# AI-relevant arXiv categories to query
CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CV"]

# arXiv Atom namespace map
ATOM_NS  = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


# ── Institution loading and pattern compilation ───────────────────

def load_institutions() -> dict:
    """Load institution keyword lists from data/institutions.json."""
    if not INSTITUTIONS_FILE.exists():
        log.error("institutions.json not found at %s", INSTITUTIONS_FILE)
        sys.exit(1)
    with open(INSTITUTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def compile_patterns(keywords: list[str]) -> list[re.Pattern]:
    """Compile a list of keyword strings into word-boundary regex patterns."""
    return [
        re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for kw in keywords
    ]


def build_pattern_sets(institutions: dict) -> dict:
    """
    Return compiled patterns for affiliation and abstract matching.

    Structure:
      {
        "affiliation": {"US": [...], "China": [...], "Other": [...]},
        "abstract":    {"US": [...], "China": [...], "Other": [...]},
      }
    """
    return {
        "affiliation": {
            "US":    compile_patterns(institutions["us"]["affiliation"]),
            "China": compile_patterns(institutions["china"]["affiliation"]),
            "Other": compile_patterns(institutions["other"]["affiliation"]),
        },
        "abstract": {
            "US":    compile_patterns(institutions["us"]["abstract"]),
            "China": compile_patterns(institutions["china"]["abstract"]),
            "Other": compile_patterns(institutions["other"]["abstract"]),
        },
    }


# ── Classification ────────────────────────────────────────────────

def score_text(text: str, patterns_by_country: dict[str, list]) -> dict[str, int]:
    """Count keyword hits per country for a single text string."""
    scores = {c: 0 for c in patterns_by_country}
    for country, pats in patterns_by_country.items():
        for pat in pats:
            if pat.search(text):
                scores[country] += 1
    return scores


def classify_paper(affiliations: list[str], abstract: str, pattern_sets: dict) -> str:
    """
    Classify a paper as US / China / Other / Unknown.

    Strategy:
    - If affiliation fields are present, use them (more reliable).
    - Otherwise fall back to the first 600 chars of abstract text.
    - If both US and China score > 0, mark Unknown (likely collaboration).
    - Return the country with the highest score, or Unknown if tied / zero.
    """
    if affiliations:
        text = " | ".join(affiliations)
        patterns = pattern_sets["affiliation"]
    else:
        text = abstract[:600]
        patterns = pattern_sets["abstract"]

    scores = score_text(text, patterns)

    us    = scores["US"]
    china = scores["China"]
    other = scores["Other"]

    # Mixed US+China signals → Unknown (can't attribute cleanly)
    if us > 0 and china > 0:
        return "Unknown"

    best_count = max(us, china, other)
    if best_count == 0:
        return "Unknown"

    if us == best_count:
        return "US"
    if china == best_count:
        return "China"
    return "Other"


# ── arXiv API fetching ────────────────────────────────────────────

def fetch_papers_for_category(category: str, cutoff: datetime) -> list[dict]:
    """
    Fetch up to RESULTS_PER_CAT papers for one arXiv category.

    Returns only papers published after cutoff (sorted descending, so we
    stop early once we hit a paper older than the window).
    """
    url = (
        f"{ARXIV_API_BASE}"
        f"?search_query=cat:{category}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&start=0&max_results={RESULTS_PER_CAT}"
    )

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning("Request failed for category '%s': %s", category, e)
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        log.warning("XML parse error for category '%s': %s", category, e)
        return []

    papers = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        # Published date
        published_str = (entry.findtext(f"{{{ATOM_NS}}}published") or "").strip()
        try:
            published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        # Papers are sorted newest-first; once we hit one older than cutoff, stop
        if published_dt < cutoff:
            break

        arxiv_id = (entry.findtext(f"{{{ATOM_NS}}}id") or "").strip()
        title    = (entry.findtext(f"{{{ATOM_NS}}}title") or "").strip().replace("\n", " ")
        abstract = (entry.findtext(f"{{{ATOM_NS}}}summary") or "").strip().replace("\n", " ")

        authors      = []
        affiliations = []
        for author_el in entry.findall(f"{{{ATOM_NS}}}author"):
            name = (author_el.findtext(f"{{{ATOM_NS}}}name") or "").strip()
            if name:
                authors.append(name)
            affil = (author_el.findtext(f"{{{ARXIV_NS}}}affiliation") or "").strip()
            if affil:
                affiliations.append(affil)

        cats = [
            c.get("term", "")
            for c in entry.findall(f"{{{ATOM_NS}}}category")
        ]

        papers.append({
            "id":           arxiv_id,
            "title":        title,
            "authors":      authors,
            "affiliations": affiliations,
            "abstract":     abstract,
            "published":    published_str,
            "categories":   cats,
        })

    return papers


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    institutions  = load_institutions()
    pattern_sets  = build_pattern_sets(institutions)
    cutoff        = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    log.info("Window: last %d days (after %s UTC)", WINDOW_DAYS, cutoff.date())
    log.info("Categories: %s", ", ".join(CATEGORIES))
    log.info("Max papers per category: %d", RESULTS_PER_CAT)

    # ── Fetch and deduplicate papers across categories ────────────
    seen_ids: set[str] = set()
    all_raw:  list[dict] = []

    for cat in CATEGORIES:
        log.info("Fetching: %s", cat)
        papers = fetch_papers_for_category(cat, cutoff)
        new_count = 0
        for p in papers:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                all_raw.append(p)
                new_count += 1
        log.info("  → %d returned, %d new after dedup", len(papers), new_count)
        time.sleep(RATE_LIMIT_SLEEP)

    log.info("Total unique papers within window: %d", len(all_raw))

    # ── Classify ──────────────────────────────────────────────────
    summary = {"US": 0, "China": 0, "Other": 0, "Unknown": 0}
    output_papers: list[dict] = []

    for p in all_raw:
        country = classify_paper(p["affiliations"], p["abstract"], pattern_sets)
        summary[country] += 1
        output_papers.append({
            "id":         p["id"],
            "title":      p["title"],
            "authors":    p["authors"][:MAX_AUTHORS_OUT],
            "country":    country,
            "published":  p["published"],
            "categories": p["categories"],
            "source":     "arxiv",
        })

    # Sort newest first
    output_papers.sort(key=lambda x: x["published"], reverse=True)
    total = len(output_papers)

    # ── Build output ──────────────────────────────────────────────
    output = {
        "dimension":   "talent",
        "metric_key":  "papers_last_12_months",
        "description": (
            f"AI-related research papers (cs.AI, cs.LG, cs.CL, cs.CV) "
            f"sampled from arXiv in the last {WINDOW_DAYS} days, classified "
            "by country of institution. A proxy for research output velocity, "
            "not a complete census of all AI research activity."
        ),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW_DAYS,
        "source": {
            "name": "arXiv API",
            "url":  ARXIV_API_BASE,
            "note": (
                f"Up to {RESULTS_PER_CAT} papers per category, sorted by submission "
                "date descending. Deduplicated across categories. Public submissions only."
            ),
        },
        "summary": {
            "US":      summary["US"],
            "China":   summary["China"],
            "Other":   summary["Other"],
            "Unknown": summary["Unknown"],
            "total":   total,
        },
        "papers": output_papers,
        "methodology_note": (
            "Papers are classified by country using keyword matching against author "
            "affiliation fields (when provided by arXiv) or the first 600 characters "
            "of each abstract as a fallback. arXiv does not reliably include affiliation "
            "metadata, so most classification relies on abstract text — this introduces "
            "noise and a higher Unknown rate than ideal. "
            "Papers with both US and China keyword matches are classified as Unknown "
            "(likely international collaborations). "
            f"Coverage is capped at {RESULTS_PER_CAT} papers per category due to API limits. "
            "For high-volume categories (cs.LG, cs.CV), this covers only the most recent "
            "weeks or months of the 12-month window, not the full year. "
            "The metric measures arXiv submission volume, not citation impact, "
            "researcher headcount, or research quality. "
            "Chinese institutions may also publish to domestic preprint platforms "
            "(ChinaXiv, etc.), which are not captured here."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info(
        "Summary: US=%d  China=%d  Other=%d  Unknown=%d  Total=%d",
        summary["US"], summary["China"], summary["Other"], summary["Unknown"], total,
    )


if __name__ == "__main__":
    main()
