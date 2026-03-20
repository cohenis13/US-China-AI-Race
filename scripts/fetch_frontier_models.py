#!/usr/bin/env python3
"""
Fetch frontier model data from Hugging Face Hub API.

Classifies models by country based on the manual lab mapping in data/labs.json.
Outputs cleaned, timestamped data to data/frontier_models.json.

Usage:
    pip install requests
    python scripts/fetch_frontier_models.py

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
LABS_FILE   = ROOT / "data" / "labs.json"
OUTPUT_FILE = ROOT / "data" / "frontier_models.json"

# ── Config ───────────────────────────────────────────────────────
WINDOW_DAYS      = 30
HF_API_BASE      = "https://huggingface.co/api/models"
REQUEST_TIMEOUT  = 20         # seconds
RATE_LIMIT_SLEEP = 0.4        # seconds between API calls (be polite)
RESULTS_PER_AUTHOR = 100      # max models to fetch per author


def load_labs() -> list[dict]:
    """Load the lab-to-country mapping from data/labs.json."""
    if not LABS_FILE.exists():
        log.error("labs.json not found at %s", LABS_FILE)
        sys.exit(1)
    with open(LABS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["labs"]


def parse_hf_datetime(dt_str: str) -> datetime | None:
    """Parse a Hugging Face ISO 8601 datetime string to a UTC-aware datetime."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_models_for_author(author: str, cutoff: datetime) -> list[dict]:
    """
    Fetch models for a given HF author updated after cutoff.

    Returns a list of model dicts (filtered to within the rolling window).
    Returns [] on failure (non-fatal — logged as warning).
    """
    url = (
        f"{HF_API_BASE}"
        f"?author={author}"
        f"&sort=lastModified"
        f"&direction=-1"
        f"&limit={RESULTS_PER_AUTHOR}"
    )
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        models = resp.json()
    except requests.exceptions.HTTPError as e:
        log.warning("HTTP error for author '%s': %s", author, e)
        return []
    except requests.exceptions.RequestException as e:
        log.warning("Request failed for author '%s': %s", author, e)
        return []

    recent = []
    for m in models:
        # Try both field names — HF API has changed over time
        last_mod_str = m.get("lastModified") or m.get("updatedAt") or ""
        dt = parse_hf_datetime(last_mod_str)
        if dt is None or dt < cutoff:
            continue
        recent.append({
            "model_id":      m.get("id") or m.get("modelId", ""),
            "author":        author,
            "last_modified": last_mod_str,
            "downloads":     m.get("downloads", 0),
            "likes":         m.get("likes", 0),
            "pipeline_tag":  m.get("pipeline_tag", ""),
        })
    return recent


def classify_country(country: str) -> str:
    """Normalize country label to US / China / Other / Unknown.

    - US      : US-headquartered lab
    - China   : China-headquartered lab
    - Other   : identified lab headquartered outside US and China (e.g. Mistral AI)
    - Unknown : genuinely unclassifiable or not in labs.json
    """
    if country == "US":
        return "US"
    if country == "China":
        return "China"
    if country == "Other":
        return "Other"
    return "Unknown"


def main() -> None:
    labs   = load_labs()
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    log.info("Window: last %d days (after %s UTC)", WINDOW_DAYS, cutoff.date())
    log.info("Labs loaded: %d entries", len(labs))

    all_models: list[dict] = []
    raw_summary: dict[str, int] = {}

    for lab in labs:
        lab_name   = lab["name"]
        raw_country = lab.get("country", "Unknown")
        country    = classify_country(raw_country)
        hf_authors = lab.get("hf_authors", [])

        for author in hf_authors:
            log.info("  Fetching %-30s [%s / %s]", author, lab_name, country)
            models = fetch_models_for_author(author, cutoff)

            for m in models:
                m["lab_name"] = lab_name
                m["country"]  = country
                all_models.append(m)

            count = len(models)
            raw_summary[country] = raw_summary.get(country, 0) + count
            log.info("    → %d model(s) found", count)

            time.sleep(RATE_LIMIT_SLEEP)

    # Sort by most recently modified first
    all_models.sort(key=lambda x: x["last_modified"], reverse=True)

    # Build summary counts
    us_count      = raw_summary.get("US", 0)
    china_count   = raw_summary.get("China", 0)
    other_count   = raw_summary.get("Other", 0)
    unknown_count = raw_summary.get("Unknown", 0)
    total         = len(all_models)

    output = {
        "dimension":    "frontier_models",
        "metric_key":   "recent_model_updates",
        "labs_tracked": len(labs),
        "description": (
            f"Public model update activity on Hugging Face Hub from tracked labs "
            f"in the last {WINDOW_DAYS} days, classified by lab country (US / China / Other / Unknown). "
            "This is a proxy metric for lab activity, not a definitive ranking of frontier model capability."
        ),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW_DAYS,
        "source": {
            "name": "Hugging Face Hub API",
            "url":  HF_API_BASE,
            "note": "Models filtered by a curated list of known labs (data/labs.json). Public models only.",
        },
        "summary": {
            "US":      us_count,
            "China":   china_count,
            "Other":   other_count,
            "Unknown": unknown_count,
            "total":   total,
        },
        "models": all_models,
        "methodology_note": (
            "Models are attributed to countries based on the manual lab mapping in "
            "data/labs.json. Only models last modified within the rolling 30-day "
            "window are counted. Four categories are used: US (US-headquartered labs), "
            "China (China-headquartered labs), Other (identified labs outside US and China, "
            "e.g. Mistral AI in France), and Unknown (genuinely unclassifiable). "
            "This is an imperfect proxy — it captures public model update activity on "
            "Hugging Face Hub, not a comprehensive census of all frontier AI development. "
            "Closed models (GPT-4o, Claude, Gemini Ultra) are not counted. "
            "China-affiliated labs that publish primarily to domestic platforms "
            "(ModelScope, etc.) may be undercounted. "
            "NVIDIA publishes models across many specialized domains (robotics, medical imaging, "
            "weather forecasting) and re-hosts some third-party model weights; its raw count "
            "may not reflect general-purpose frontier model activity."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("Summary: US=%d  China=%d  Other=%d  Unknown=%d  Total=%d",
             us_count, china_count, other_count, unknown_count, total)


if __name__ == "__main__":
    main()
