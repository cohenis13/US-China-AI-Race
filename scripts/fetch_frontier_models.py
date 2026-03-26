#!/usr/bin/env python3
"""
Fetch frontier AI model data — two-proxy composite index.

PROXIES
  1. Capability score (60%): US share of top-N models on the Artificial
     Analysis Intelligence Index leaderboard, read from the manually-
     maintained data/leaderboard_snapshot.json (updated weekly).
     Directly answers: "who has the most capable models right now?"

  2. Output score (40%): US share of notable AI models released in the
     last 2 years, from the Epoch AI notable_ai_models.csv dataset.
     Answers: "who is producing frontier-class models at what pace?"

COMPOSITE SCORING
  Each proxy is scored as share-of-combined (US + China = 100).
  Composite = 0.60 * capability_share + 0.40 * output_share.
  US composite + China composite ≈ 100 by construction.

WHY THIS APPROACH?
  The previous HF Hub activity count was a noisy proxy that missed all
  closed models (GPT-4o, Claude, Gemini, DeepSeek) — the most capable
  systems. The new approach uses actual capability rankings for the
  primary signal and release counts for context.

DATA SOURCES
  - Leaderboard: https://artificialanalysis.ai/leaderboards/models
    (manually updated weekly in data/leaderboard_snapshot.json)
  - Epoch AI: https://epoch.ai/data/notable_ai_models.csv
    (fetched automatically; updated ~weekly by Epoch)

OUTPUT: data/frontier_models.json
"""

import csv
import io
import json
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required.")
    print("Install it with:  pip install requests")
    sys.exit(1)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT               = Path(__file__).resolve().parent.parent
LEADERBOARD_FILE   = ROOT / "data" / "leaderboard_snapshot.json"
OUTPUT_FILE        = ROOT / "data" / "frontier_models.json"

# ── Config ────────────────────────────────────────────────────────────────────
EPOCH_CSV_URL    = "https://epoch.ai/data/notable_ai_models.csv"
REQUEST_TIMEOUT  = 30
WINDOW_YEARS     = 2      # look back 2 years for output score
TOP_N            = 20     # how many leaderboard models to count

WEIGHTS = {
    "capability": 0.60,
    "output":     0.40,
}

# Epoch AI CSV uses full country names
US_COUNTRY  = "United States"
CN_COUNTRY  = "China"

MAILTO = "ai-tracker@github-actions"


# ── Helpers ───────────────────────────────────────────────────────────────────

def share_score(us: int | float, cn: int | float) -> tuple[float, float]:
    """Return (us_share, cn_share) as percentages summing to 100."""
    total = us + cn
    if total == 0:
        return 50.0, 50.0
    us_share = round((us / total) * 100.0, 1)
    cn_share = round(100.0 - us_share, 1)
    return us_share, cn_share


# ── Proxy 1: Capability score from leaderboard snapshot ───────────────────────

def load_leaderboard() -> dict:
    if not LEADERBOARD_FILE.exists():
        log.error("leaderboard_snapshot.json not found at %s", LEADERBOARD_FILE)
        sys.exit(1)
    with open(LEADERBOARD_FILE, encoding="utf-8") as f:
        return json.load(f)


def compute_capability_score(snapshot: dict) -> dict:
    """
    Count US and China models in the top-N leaderboard.
    Returns a dict with counts, shares, and the model list.
    """
    models = snapshot.get("top_models", [])[:TOP_N]

    us_count    = sum(1 for m in models if m.get("country") == "US")
    china_count = sum(1 for m in models if m.get("country") == "China")
    other_count = sum(1 for m in models if m.get("country") == "Other")

    us_share, cn_share = share_score(us_count, china_count)

    log.info("── Proxy 1: Capability (leaderboard top-%d) ──────────────────", TOP_N)
    log.info("  US=%d  China=%d  Other=%d  → US_share=%.1f%%",
             us_count, china_count, other_count, us_share)

    if snapshot.get("needs_update"):
        log.warning("  leaderboard_snapshot.json has needs_update=true — data may be stale")

    return {
        "us_count":       us_count,
        "china_count":    china_count,
        "other_count":    other_count,
        "us_share":       us_share,
        "cn_share":       cn_share,
        "top_n":          TOP_N,
        "snapshot_date":  snapshot.get("last_updated", "unknown"),
        "source":         snapshot.get("source", "Artificial Analysis Intelligence Index"),
        "source_url":     snapshot.get("source_url", ""),
        "models":         models,
    }


# ── Proxy 2: Output score from Epoch AI ───────────────────────────────────────

def fetch_epoch_csv() -> str | None:
    """Download the Epoch AI notable models CSV. Returns raw text or None."""
    headers = {"User-Agent": f"ai-race-tracker/1.0 (mailto:{MAILTO})"}
    try:
        resp = requests.get(EPOCH_CSV_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as e:
        log.warning("Epoch AI CSV fetch failed: %s", e)
        return None


def parse_epoch_csv(raw_csv: str, cutoff_date: str) -> dict:
    """
    Parse the Epoch AI CSV and count US and China notable models
    published since cutoff_date (YYYY-MM-DD).
    Returns counts and a list of recent models for the table.
    """
    reader = csv.DictReader(io.StringIO(raw_csv))

    us_count    = 0
    china_count = 0
    recent_models: list[dict] = []

    for row in reader:
        pub_date = (row.get("Publication date") or "").strip()
        if not pub_date or pub_date < cutoff_date:
            continue

        country = (row.get("Country (of organization)") or "").strip()
        model   = (row.get("Model") or "").strip()
        org     = (row.get("Organization") or "").strip()
        compute = (row.get("Training compute (FLOP)") or "").strip()
        frontier = (row.get("Frontier model") or "").strip().lower()

        if country == US_COUNTRY:
            us_count += 1
        elif country == CN_COUNTRY:
            china_count += 1

        recent_models.append({
            "model":       model,
            "developer":   org,
            "country_raw": country,
            "country":     "US" if country == US_COUNTRY else ("China" if country == CN_COUNTRY else "Other"),
            "published":   pub_date,
            "compute":     compute,
            "frontier":    frontier == "yes",
        })

    # Sort by date descending for display
    recent_models.sort(key=lambda x: x["published"], reverse=True)

    return {
        "us_count":      us_count,
        "china_count":   china_count,
        "total_parsed":  us_count + china_count,
        "window_years":  WINDOW_YEARS,
        "cutoff_date":   cutoff_date,
        "recent_models": recent_models[:20],
    }


def compute_output_score(epoch_data: dict) -> dict:
    us_count    = epoch_data["us_count"]
    china_count = epoch_data["china_count"]
    us_share, cn_share = share_score(us_count, china_count)

    log.info("── Proxy 2: Output (Epoch AI, last %dy) ──────────────────────", WINDOW_YEARS)
    log.info("  US=%d  China=%d  → US_share=%.1f%%", us_count, china_count, us_share)

    return {
        "us_count":    us_count,
        "china_count": china_count,
        "us_share":    us_share,
        "cn_share":    cn_share,
        **{k: v for k, v in epoch_data.items() if k not in ("us_count", "china_count")},
    }


# ── Composite ─────────────────────────────────────────────────────────────────

def compute_composite(cap: dict, out: dict) -> tuple[float, float]:
    us_comp = round(
        WEIGHTS["capability"] * cap["us_share"] +
        WEIGHTS["output"]     * out["us_share"],
        1,
    )
    cn_comp = round(100.0 - us_comp, 1)
    return us_comp, cn_comp


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today      = datetime.now(timezone.utc).date()
    cutoff     = (today - timedelta(days=WINDOW_YEARS * 365)).isoformat()

    # ── Proxy 1: Capability ───────────────────────────────────────────────────
    snapshot = load_leaderboard()
    cap      = compute_capability_score(snapshot)

    # ── Proxy 2: Output ───────────────────────────────────────────────────────
    raw_csv  = fetch_epoch_csv()
    if raw_csv is None:
        log.error("Could not fetch Epoch AI CSV — aborting")
        sys.exit(1)
    epoch_data = parse_epoch_csv(raw_csv, cutoff)
    out        = compute_output_score(epoch_data)

    # ── Composite ─────────────────────────────────────────────────────────────
    us_comp, cn_comp = compute_composite(cap, out)

    log.info("")
    log.info("Composite: US=%.1f  CN=%.1f", us_comp, cn_comp)

    # ── Build output ──────────────────────────────────────────────────────────
    output = {
        "dimension":   "frontier_models",
        "metric_key":  "frontier_model_composite",
        "title":       "Frontier AI Models — U.S. vs China",
        "subtitle": (
            f"Two-proxy composite: capability ranking share (60%, top-{TOP_N} leaderboard) "
            f"+ notable model output share (40%, Epoch AI, last {WINDOW_YEARS} years). "
            "Each proxy scored as share-of-combined (US + China = 100)."
        ),
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "summary": {
            "US": {
                "composite_score": us_comp,
                "effective_weights": WEIGHTS,
                "proxies": {
                    "capability": {
                        "raw_value":     cap["us_count"],
                        "unit":          f"models in top {TOP_N} (leaderboard)",
                        "share_score":   cap["us_share"],
                        "top_n":         TOP_N,
                        "snapshot_date": cap["snapshot_date"],
                        "note": (
                            f"US has {cap['us_count']} of the top {TOP_N} models on the "
                            f"Artificial Analysis Intelligence Index "
                            f"(snapshot: {cap['snapshot_date']})."
                        ),
                    },
                    "output": {
                        "raw_value":   out["us_count"],
                        "unit":        f"notable AI models (last {WINDOW_YEARS}y, Epoch AI)",
                        "share_score": out["us_share"],
                        "window_years": WINDOW_YEARS,
                        "note": (
                            f"US-based labs released {out['us_count']} notable AI models "
                            f"in the last {WINDOW_YEARS} years per Epoch AI database."
                        ),
                    },
                },
            },
            "China": {
                "composite_score": cn_comp,
                "effective_weights": WEIGHTS,
                "proxies": {
                    "capability": {
                        "raw_value":     cap["china_count"],
                        "unit":          f"models in top {TOP_N} (leaderboard)",
                        "share_score":   cap["cn_share"],
                        "top_n":         TOP_N,
                        "snapshot_date": cap["snapshot_date"],
                        "note": (
                            f"China has {cap['china_count']} of the top {TOP_N} models on the "
                            f"Artificial Analysis Intelligence Index "
                            f"(snapshot: {cap['snapshot_date']})."
                        ),
                    },
                    "output": {
                        "raw_value":   out["china_count"],
                        "unit":        f"notable AI models (last {WINDOW_YEARS}y, Epoch AI)",
                        "share_score": out["cn_share"],
                        "window_years": WINDOW_YEARS,
                        "note": (
                            f"China-based labs released {out['china_count']} notable AI models "
                            f"in the last {WINDOW_YEARS} years per Epoch AI database."
                        ),
                    },
                },
            },
        },
        "leaderboard": {
            "source":       cap["source"],
            "source_url":   cap["source_url"],
            "last_updated": cap["snapshot_date"],
            "top_n":        TOP_N,
            "models":       cap["models"],
            "us_count":     cap["us_count"],
            "china_count":  cap["china_count"],
            "other_count":  cap["other_count"],
        },
        "epoch_output": {
            "source":        "Epoch AI notable_ai_models.csv",
            "source_url":    EPOCH_CSV_URL,
            "window_years":  WINDOW_YEARS,
            "cutoff_date":   cutoff,
            "us_count":      out["us_count"],
            "china_count":   out["china_count"],
            "recent_models": epoch_data["recent_models"],
        },
        "composite_construction": {
            "method":  "Weighted average of two share-of-combined scores.",
            "weights": WEIGHTS,
            "note": (
                "Capability score (60%): US share of top-20 Artificial Analysis models. "
                "Output score (40%): US share of Epoch AI notable models in last 2 years. "
                "Both proxies use US/(US+China)*100; Other-country models are excluded "
                "from the denominator."
            ),
        },
        "interpretive_sentence": (
            f"On a composite of leaderboard capability ranking (60%) and notable model "
            f"output (40%), the US scores {us_comp:.1f} and China scores {cn_comp:.1f} "
            f"out of 100. "
            f"US has {cap['us_count']} of the top {TOP_N} models on AI benchmarks; "
            f"China has {cap['china_count']}. "
            f"On model output, US released {out['us_count']} notable models vs "
            f"China's {out['china_count']} in the last {WINDOW_YEARS} years."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info(
        "Capability (top-%d):  US=%d  CN=%d  US_share=%.1f%%",
        TOP_N, cap["us_count"], cap["china_count"], cap["us_share"],
    )
    log.info(
        "Output (Epoch, %dy): US=%d  CN=%d  US_share=%.1f%%",
        WINDOW_YEARS, out["us_count"], out["china_count"], out["us_share"],
    )
    log.info("Composite:           US=%.1f  CN=%.1f", us_comp, cn_comp)


if __name__ == "__main__":
    main()
