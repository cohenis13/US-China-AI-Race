#!/usr/bin/env python3
"""
Fetch frontier AI model data — two-proxy composite index.

PROXIES
  1. Capability score (60%): US share of top-20 models on the Chatbot Arena
     leaderboard (Arena Elo), loaded from the HuggingFace dataset
     mathewhe/chatbot-arena-elo. Reflects human-preference rankings across
     open and closed models from both US and Chinese labs.

  2. Output score (40%): US share of notable AI models released in the last
     2 years, from the Epoch AI notable_ai_models.csv dataset.

COMPOSITE SCORING
  Each proxy: US share of combined US+China (Other excluded from denominator).
  Composite = 0.60 * capability_share + 0.40 * output_share.

OUTPUT: data/frontier_models.json
         data/leaderboard_snapshot.json  (updated with current Elo rankings)
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
    print("Error: 'requests' package is required.  pip install requests")
    sys.exit(1)

try:
    from datasets import load_dataset
except ImportError:
    print("Error: 'datasets' package is required.  pip install datasets")
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
HF_DATASET_ID    = "mathewhe/chatbot-arena-elo"
EPOCH_CSV_URL    = "https://epoch.ai/data/notable_ai_models.csv"
REQUEST_TIMEOUT  = 30
WINDOW_YEARS     = 2
TOP_N            = 20

WEIGHTS = {"capability": 0.60, "output": 0.40}

EPOCH_US_COUNTRY = "United States of America"
EPOCH_CN_COUNTRY = "China"

MAILTO = "ai-tracker@github-actions"

# ── Organization → country mapping (Arena dataset) ───────────────────────────
US_ORGS = {
    "OpenAI", "Anthropic", "Google", "Meta", "xAI", "Microsoft", "Amazon",
    "Cohere", "Ai2", "Allen AI", "AllenAI/UW", "HuggingFace", "IBM", "LMSYS",
    "MosaicML", "NexusFlow", "Nexusflow", "Nomic AI", "NousResearch", "Nvidia",
    "Princeton", "Stanford", "Together AI", "UC Berkeley", "UW", "Databricks",
    "Snowflake", "Cognitive Computations", "Reka AI",
}

CN_ORGS = {
    "DeepSeek", "DeepSeek AI", "Alibaba", "Moonshot", "MiniMax", "Tencent",
    "Zhipu", "Zhipu AI", "01 AI", "StepFun", "Tsinghua", "InternLM", "Baidu",
    "ByteDance", "Huawei", "Baichuan",
}


def map_org_to_country(org: str) -> str:
    if not org:
        return "Other"
    org_stripped = org.strip()
    if org_stripped in US_ORGS:
        return "US"
    if org_stripped in CN_ORGS:
        return "China"
    # Fallback: substring check for common patterns
    org_lower = org_stripped.lower()
    if any(x in org_lower for x in ["openai", "anthropic", "google", "deepmind", "meta ", "microsoft", "amazon", "nvidia"]):
        return "US"
    if any(x in org_lower for x in ["deepseek", "alibaba", "qwen", "baidu", "tencent", "bytedance", "moonshot", "minimax", "zhipu", "huawei"]):
        return "China"
    return "Other"


# ── Helpers ───────────────────────────────────────────────────────────────────

def share_score(us: float, cn: float) -> tuple[float, float]:
    total = us + cn
    if total == 0:
        return 50.0, 50.0
    us_share = round((us / total) * 100.0, 1)
    return us_share, round(100.0 - us_share, 1)


# ── Proxy 1: Capability — Chatbot Arena Elo ───────────────────────────────────

def fetch_arena_leaderboard() -> list[dict]:
    """
    Load mathewhe/chatbot-arena-elo from HuggingFace, return top-N models
    sorted by Arena Score descending, with country mapping applied.
    """
    log.info("── Proxy 1: Loading Chatbot Arena Elo from HuggingFace ────────")
    ds  = load_dataset(HF_DATASET_ID)
    df  = ds["train"].to_pandas()

    # Sort by Arena Score descending; keep top N
    df = df.sort_values("Arena Score", ascending=False).reset_index(drop=True)

    models = []
    for _, row in df.iterrows():
        model   = str(row.get("Model") or "").strip()
        org     = str(row.get("Organization") or "").strip()
        elo     = row.get("Arena Score")
        country = map_org_to_country(org)
        if not model:
            continue
        models.append({
            "rank":        len(models) + 1,
            "model":       model,
            "developer":   org,
            "country":     country,
            "elo":         int(elo) if elo is not None else None,
        })
        if len(models) >= TOP_N:
            break

    log.info("  Loaded %d models from Arena dataset", len(models))
    for m in models:
        log.info("    #%-2d %-45s %-8s Elo=%s", m["rank"], m["model"], m["country"], m["elo"])

    return models


def compute_capability_score(models: list[dict]) -> dict:
    us_count    = sum(1 for m in models if m["country"] == "US")
    cn_count    = sum(1 for m in models if m["country"] == "China")
    other_count = sum(1 for m in models if m["country"] == "Other")
    us_share, cn_share = share_score(us_count, cn_count)

    log.info("  US=%d  China=%d  Other=%d  → US_share=%.1f%%",
             us_count, cn_count, other_count, us_share)
    return {
        "us_count":    us_count,
        "china_count": cn_count,
        "other_count": other_count,
        "us_share":    us_share,
        "cn_share":    cn_share,
        "top_n":       TOP_N,
        "models":      models,
    }


def update_leaderboard_snapshot(models: list[dict], today: str) -> None:
    """Overwrite leaderboard_snapshot.json with fresh Arena data."""
    snapshot = {
        "_instructions": [
            "Auto-updated daily from mathewhe/chatbot-arena-elo on HuggingFace.",
            "Source: LMSYS Chatbot Arena (human preference Elo rankings).",
            "Do not edit manually — changes will be overwritten on next run."
        ],
        "source":       "LMSYS Chatbot Arena via mathewhe/chatbot-arena-elo",
        "source_url":   "https://huggingface.co/datasets/mathewhe/chatbot-arena-elo",
        "last_updated": today,
        "needs_update": False,
        "top_models":   models,
    }
    LEADERBOARD_FILE.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    log.info("  leaderboard_snapshot.json updated (%d models)", len(models))


# ── Proxy 2: Output — Epoch AI ────────────────────────────────────────────────

def fetch_epoch_csv() -> str | None:
    headers = {"User-Agent": f"ai-race-tracker/1.0 (mailto:{MAILTO})"}
    try:
        resp = requests.get(EPOCH_CSV_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException as e:
        log.warning("Epoch AI CSV fetch failed: %s", e)
        return None


def parse_epoch_output(raw_csv: str, cutoff_date: str) -> dict:
    reader      = csv.DictReader(io.StringIO(raw_csv))
    us_count    = 0
    china_count = 0
    recent: list[dict] = []

    for row in reader:
        pub_date = (row.get("Publication date") or "").strip()
        if not pub_date or pub_date < cutoff_date:
            continue
        country_raw   = (row.get("Country (of organization)") or "").strip()
        country_parts = [c.strip() for c in country_raw.split(",") if c.strip()]
        is_us    = any(c == EPOCH_US_COUNTRY for c in country_parts)
        is_china = any(c == EPOCH_CN_COUNTRY for c in country_parts)
        model    = (row.get("Model") or "").strip()
        org      = (row.get("Organization") or "").strip()
        compute  = (row.get("Training compute (FLOP)") or "").strip()
        frontier = (row.get("Frontier model") or "").strip().lower() == "yes"
        country  = "US" if is_us else ("China" if is_china else "Other")

        if is_us:
            us_count += 1
        elif is_china:
            china_count += 1

        recent.append({
            "model":     model,
            "developer": org,
            "country":   country,
            "published": pub_date,
            "compute":   compute,
            "frontier":  frontier,
        })

    recent.sort(key=lambda x: x["published"], reverse=True)
    us_share, cn_share = share_score(us_count, china_count)

    log.info("── Proxy 2: Epoch AI output (last %dy) ────────────────────────", WINDOW_YEARS)
    log.info("  US=%d  China=%d  → US_share=%.1f%%", us_count, china_count, us_share)

    return {
        "us_count":      us_count,
        "china_count":   china_count,
        "us_share":      us_share,
        "cn_share":      cn_share,
        "window_years":  WINDOW_YEARS,
        "cutoff_date":   cutoff_date,
        "recent_models": recent[:20],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today   = datetime.now(timezone.utc).date()
    cutoff  = (today - timedelta(days=WINDOW_YEARS * 365)).isoformat()
    today_s = today.isoformat()

    # ── Proxy 1: Capability ───────────────────────────────────────────────────
    arena_models = fetch_arena_leaderboard()
    cap          = compute_capability_score(arena_models)
    update_leaderboard_snapshot(arena_models, today_s)

    # ── Proxy 2: Output ───────────────────────────────────────────────────────
    raw_csv = fetch_epoch_csv()
    if raw_csv is None:
        log.error("Could not fetch Epoch AI CSV — aborting")
        sys.exit(1)
    out = parse_epoch_output(raw_csv, cutoff)

    # ── Composite ─────────────────────────────────────────────────────────────
    us_comp = round(WEIGHTS["capability"] * cap["us_share"] + WEIGHTS["output"] * out["us_share"], 1)
    cn_comp = round(100.0 - us_comp, 1)

    log.info("")
    log.info("Composite: US=%.1f  CN=%.1f", us_comp, cn_comp)

    # ── Build output ──────────────────────────────────────────────────────────
    output = {
        "dimension":   "frontier_models",
        "metric_key":  "frontier_model_composite",
        "title":       "Frontier AI Models — U.S. vs China",
        "subtitle": (
            f"Two-proxy composite: Arena Elo capability ranking share (60%, top-{TOP_N}) "
            f"+ notable model output share (40%, Epoch AI, last {WINDOW_YEARS} years). "
            "Each proxy: US share of combined US+China."
        ),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "summary": {
            "US": {
                "composite_score": us_comp,
                "effective_weights": WEIGHTS,
                "proxies": {
                    "capability": {
                        "raw_value":   cap["us_count"],
                        "unit":        f"models in top {TOP_N} (Arena Elo)",
                        "share_score": cap["us_share"],
                        "top_n":       TOP_N,
                        "source":      "LMSYS Chatbot Arena (mathewhe/chatbot-arena-elo)",
                    },
                    "output": {
                        "raw_value":   out["us_count"],
                        "unit":        f"notable AI models released (last {WINDOW_YEARS}y)",
                        "share_score": out["us_share"],
                        "window_years": WINDOW_YEARS,
                        "source":      "Epoch AI notable_ai_models.csv",
                    },
                },
            },
            "China": {
                "composite_score": cn_comp,
                "effective_weights": WEIGHTS,
                "proxies": {
                    "capability": {
                        "raw_value":   cap["china_count"],
                        "unit":        f"models in top {TOP_N} (Arena Elo)",
                        "share_score": cap["cn_share"],
                        "top_n":       TOP_N,
                        "source":      "LMSYS Chatbot Arena (mathewhe/chatbot-arena-elo)",
                    },
                    "output": {
                        "raw_value":   out["china_count"],
                        "unit":        f"notable AI models released (last {WINDOW_YEARS}y)",
                        "share_score": out["cn_share"],
                        "window_years": WINDOW_YEARS,
                        "source":      "Epoch AI notable_ai_models.csv",
                    },
                },
            },
        },
        "leaderboard": {
            "source":      "LMSYS Chatbot Arena",
            "source_url":  "https://huggingface.co/datasets/mathewhe/chatbot-arena-elo",
            "last_updated": today_s,
            "top_n":       TOP_N,
            "models":      cap["models"],
            "us_count":    cap["us_count"],
            "china_count": cap["china_count"],
            "other_count": cap["other_count"],
        },
        "epoch_output": {
            "source":        "Epoch AI notable_ai_models.csv",
            "source_url":    EPOCH_CSV_URL,
            "window_years":  WINDOW_YEARS,
            "cutoff_date":   cutoff,
            "us_count":      out["us_count"],
            "china_count":   out["china_count"],
            "recent_models": out["recent_models"],
        },
        "interpretive_sentence": (
            f"On a composite of Arena Elo capability ranking (60%) and notable model "
            f"output (40%), the US scores {us_comp:.1f} and China scores {cn_comp:.1f} "
            f"out of 100. "
            f"US has {cap['us_count']} of the top {TOP_N} models by human preference; "
            f"China has {cap['china_count']}. "
            f"On output, US released {out['us_count']} notable models vs "
            f"China's {out['china_count']} in the last {WINDOW_YEARS} years."
        ),
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Output written to: %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
