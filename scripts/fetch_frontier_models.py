#!/usr/bin/env python3
"""
Fetch frontier model data and build a three-proxy composite.

Proxies:
  1. Release Activity (35%)  — HuggingFace Hub 30-day model updates + ModelScope supplement
  2. Benchmark Performance (45%) — LMSYS Arena top-20 share + Epoch AI notable-model share
  3. Ecosystem Breadth (20%)  — HF download share + ModelScope platform presence

Manual data for proxies 2 and 3 is loaded from data/frontier_models_manual.json.
Outputs cleaned, timestamped data to data/frontier_models.json.

Usage:
    pip install requests
    python scripts/fetch_frontier_models.py
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
    print("Error: 'requests' package is required. Install with: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parent.parent
LABS_FILE    = ROOT / "data" / "labs.json"
MANUAL_FILE  = ROOT / "data" / "frontier_models_manual.json"
OUTPUT_FILE  = ROOT / "data" / "frontier_models.json"

WINDOW_DAYS      = 30
HF_API_BASE      = "https://huggingface.co/api/models"
REQUEST_TIMEOUT  = 20
RATE_LIMIT_SLEEP = 0.4
RESULTS_PER_AUTHOR = 100

# Proxy weights — must sum to 1.0
WEIGHT_RELEASE_ACTIVITY    = 0.35
WEIGHT_BENCHMARK_PERF      = 0.45
WEIGHT_ECOSYSTEM_BREADTH   = 0.20


def load_labs() -> list[dict]:
    if not LABS_FILE.exists():
        log.error("labs.json not found at %s", LABS_FILE)
        sys.exit(1)
    with open(LABS_FILE, encoding="utf-8") as f:
        return json.load(f)["labs"]


def load_manual() -> dict:
    if not MANUAL_FILE.exists():
        log.warning("frontier_models_manual.json not found — benchmark and ecosystem proxies will be absent")
        return {}
    with open(MANUAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def parse_hf_datetime(dt_str: str) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_models_for_author(author: str, cutoff: datetime) -> list[dict]:
    url = (
        f"{HF_API_BASE}?author={author}&sort=lastModified"
        f"&direction=-1&limit={RESULTS_PER_AUTHOR}"
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


def _share(a: float, b: float) -> tuple[float, float]:
    """Return (a_share_pct, b_share_pct) as percentages summing to 100."""
    total = a + b
    if total <= 0:
        return 50.0, 50.0
    us = round(a / total * 100, 1)
    return us, round(100.0 - us, 1)


def build_composite(
    hf_us: int, hf_cn: int,
    supp_us: int, supp_cn: int,
    manual: dict,
) -> dict:
    """
    Build the three-proxy composite summary for US and China.

    Returns a dict with summary.US and summary.China in the v2.0 schema.
    """
    # ── Proxy 1: Release Activity ─────────────────────────────────────────────
    ra_us = hf_us + supp_us
    ra_cn = hf_cn + supp_cn
    ra_us_share, ra_cn_share = _share(ra_us, ra_cn)

    ra_us_proxy = {
        "raw_value": ra_us,
        "share_score": ra_us_share,
        "hf_count": hf_us,
        "supplement_count": supp_us,
        "source_note": (
            f"HuggingFace Hub 30-day activity from tracked US labs (data/labs.json). "
            f"ModelScope supplement: {supp_us} (none applied for US in this build)."
        ),
        "sources": [
            {"name": "Hugging Face Hub API", "url": HF_API_BASE, "confidence": "High"},
        ],
    }
    ra_cn_proxy = {
        "raw_value": ra_cn,
        "share_score": ra_cn_share,
        "hf_count": hf_cn,
        "supplement_count": supp_cn,
        "source_note": (
            f"HuggingFace Hub 30-day activity from tracked China labs ({hf_cn} models) "
            f"+ ModelScope supplement for labs with limited HF presence ({supp_cn} models estimated). "
            "See data/frontier_models_manual.json for supplement detail."
        ),
        "sources": [
            {"name": "Hugging Face Hub API", "url": HF_API_BASE, "confidence": "High"},
            {"name": "ModelScope supplement (manual)", "url": "https://modelscope.cn/models", "confidence": "Low"},
        ],
    }

    # ── Proxy 2: Benchmark Performance ───────────────────────────────────────
    arena   = manual.get("lmsys_arena", {})
    epoch   = manual.get("epoch_ai_output", {})

    arena_us = arena.get("us_count", 0)
    arena_cn = arena.get("china_count", 0)
    arena_us_share, arena_cn_share = _share(arena_us, arena_cn)

    epoch_us = epoch.get("us_count", 0)
    epoch_cn = epoch.get("china_count", 0)
    epoch_us_share, epoch_cn_share = _share(epoch_us, epoch_cn)

    if arena_us + arena_cn > 0 and epoch_us + epoch_cn > 0:
        bm_us_share = round(0.5 * arena_us_share + 0.5 * epoch_us_share, 1)
        bm_cn_share = round(100.0 - bm_us_share, 1)
    elif arena_us + arena_cn > 0:
        bm_us_share, bm_cn_share = arena_us_share, arena_cn_share
    elif epoch_us + epoch_cn > 0:
        bm_us_share, bm_cn_share = epoch_us_share, epoch_cn_share
    else:
        log.warning("No benchmark data in manual file — benchmark proxy will be 50/50")
        bm_us_share, bm_cn_share = 50.0, 50.0

    arena_snap   = arena.get("snapshot_date", "unknown")
    epoch_snap   = epoch.get("snapshot_date", "unknown")
    bm_source_note = (
        f"LMSYS Arena top-{arena.get('top_n', 20)} Elo: US={arena_us}, China={arena_cn} "
        f"(snapshot {arena_snap}, confidence: {arena.get('confidence','?')}) — 50% weight. "
        f"Epoch AI notable models {epoch.get('window_years', 2)}y: US={epoch_us}, China={epoch_cn} "
        f"(snapshot {epoch_snap}, confidence: {epoch.get('confidence','?')}) — 50% weight."
    )

    bm_us_proxy = {
        "raw_value": round(bm_us_share, 1),
        "share_score": bm_us_share,
        "arena_in_top20": arena_us,
        "arena_share_score": arena_us_share,
        "epoch_notable_count": epoch_us,
        "epoch_share_score": epoch_us_share,
        "source_note": bm_source_note,
        "sources": [
            {"name": "LMSYS Chatbot Arena", "url": "https://chat.lmsys.org/", "confidence": arena.get("confidence", "Medium")},
            {"name": "Epoch AI Notable AI Models", "url": "https://epoch.ai/data/notable-ai-models", "confidence": epoch.get("confidence", "Medium-High")},
        ],
    }
    bm_cn_proxy = {
        "raw_value": round(bm_cn_share, 1),
        "share_score": bm_cn_share,
        "arena_in_top20": arena_cn,
        "arena_share_score": arena_cn_share,
        "epoch_notable_count": epoch_cn,
        "epoch_share_score": epoch_cn_share,
        "source_note": bm_source_note,
        "sources": bm_us_proxy["sources"],
    }

    # ── Proxy 3: Ecosystem Breadth ────────────────────────────────────────────
    eco      = manual.get("ecosystem_breadth", {})
    hf_dl    = eco.get("hf_downloads", {})
    ms_pres  = eco.get("modelscope_presence", {})
    pw       = eco.get("platform_weights", {"hf": 0.55, "modelscope": 0.45})

    hf_us_share = hf_dl.get("us_share_pct", 76)
    hf_cn_share = hf_dl.get("china_share_pct", 24)
    ms_us_share = ms_pres.get("us_share_pct", 10)
    ms_cn_share = ms_pres.get("china_share_pct", 90)

    eco_us_share = round(pw["hf"] * hf_us_share + pw["modelscope"] * ms_us_share, 1)
    eco_cn_share = round(100.0 - eco_us_share, 1)

    eco_coverage = (
        f"HF monthly download share {int(pw['hf']*100)}%: US={hf_us_share}%, China={hf_cn_share}% "
        f"(confidence: {hf_dl.get('confidence', '?')}). "
        f"ModelScope presence {int(pw['modelscope']*100)}%: US={ms_us_share}%, China={ms_cn_share}% "
        f"(confidence: {ms_pres.get('confidence', 'Low')} — manual estimate). "
        "China leads on ecosystem breadth when ModelScope is included."
    )
    eco_us_proxy = {
        "raw_value": eco_us_share,
        "share_score": eco_us_share,
        "hf_share": float(hf_us_share),
        "modelscope_share": float(ms_us_share),
        "coverage_note": eco_coverage,
        "sources": [
            {"name": "Hugging Face Hub API", "url": HF_API_BASE, "confidence": hf_dl.get("confidence", "Medium-High")},
            {"name": "ModelScope (manual estimate)", "url": "https://modelscope.cn/models", "confidence": "Low"},
        ],
    }
    eco_cn_proxy = {
        "raw_value": eco_cn_share,
        "share_score": eco_cn_share,
        "hf_share": float(hf_cn_share),
        "modelscope_share": float(ms_cn_share),
        "coverage_note": eco_coverage,
        "sources": eco_us_proxy["sources"],
    }

    # ── Composite ─────────────────────────────────────────────────────────────
    comp_us = round(
        WEIGHT_RELEASE_ACTIVITY  * ra_us_share +
        WEIGHT_BENCHMARK_PERF    * bm_us_share +
        WEIGHT_ECOSYSTEM_BREADTH * eco_us_share,
        1,
    )
    comp_cn = round(100.0 - comp_us, 1)

    return {
        "US": {
            "composite_score": comp_us,
            "proxies": {
                "release_activity":    ra_us_proxy,
                "benchmark_performance": bm_us_proxy,
                "ecosystem_breadth":   eco_us_proxy,
            },
        },
        "China": {
            "composite_score": comp_cn,
            "proxies": {
                "release_activity":    ra_cn_proxy,
                "benchmark_performance": bm_cn_proxy,
                "ecosystem_breadth":   eco_cn_proxy,
            },
        },
    }


def main() -> None:
    labs   = load_labs()
    manual = load_manual()
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    log.info("Window: last %d days (after %s UTC)", WINDOW_DAYS, cutoff.date())
    log.info("Labs loaded: %d entries", len(labs))

    all_models: list[dict] = []
    raw_summary: dict[str, int] = {}

    for lab in labs:
        lab_name    = lab["name"]
        country     = lab.get("country", "Unknown")
        hf_authors  = lab.get("hf_authors", [])

        for author in hf_authors:
            log.info("  Fetching %-30s [%s / %s]", author, lab_name, country)
            models = fetch_models_for_author(author, cutoff)

            for m in models:
                m["lab_name"] = lab_name
                m["country"]  = country
                all_models.append(m)

            raw_summary[country] = raw_summary.get(country, 0) + len(models)
            log.info("    → %d model(s) found", len(models))
            time.sleep(RATE_LIMIT_SLEEP)

    all_models.sort(key=lambda x: x["last_modified"], reverse=True)

    hf_us = raw_summary.get("US", 0)
    hf_cn = raw_summary.get("China", 0)

    # ModelScope supplement from manual data
    supplement = manual.get("modelscope_supplement", {})
    supp_cn = supplement.get("total_supplement_estimate", 0)
    supp_us = 0

    summary = build_composite(hf_us, hf_cn, supp_us, supp_cn, manual)

    # Leaderboard from manual snapshot
    arena = manual.get("lmsys_arena", {})
    leaderboard = {
        "source":        "LMSYS Chatbot Arena — manual snapshot, see data/frontier_models_manual.json",
        "snapshot_date": arena.get("snapshot_date", "unknown"),
        "us_count":      arena.get("us_count", 0),
        "china_count":   arena.get("china_count", 0),
        "other_count":   arena.get("other_count", 0),
        "models":        arena.get("models", []),
    }

    output = {
        "dimension":      "frontier_models",
        "metric_key":     "model_ecosystem_composite",
        "schema_version": "2.0",
        "title":          "Open Model Ecosystem Index",
        "subtitle": (
            "A three-proxy composite measuring US and Chinese AI model activity across "
            "release output, benchmark performance, and platform distribution. "
            "This is NOT a direct measure of frontier or closed-model capability."
        ),
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "window_days":  WINDOW_DAYS,
        "labs_tracked": len(labs),
        "coverage_note": (
            "Composite of: (1) release activity on HuggingFace Hub + ModelScope supplement, "
            "(2) benchmark performance from LMSYS Chatbot Arena and Epoch AI notable models, "
            "(3) ecosystem breadth across HF and ModelScope platforms. "
            "China is systematically undercounted on HF-only measures — this composite partially "
            "corrects for that via ModelScope supplement and ecosystem breadth proxy."
        ),
        "proxy_weights": {
            "release_activity":    WEIGHT_RELEASE_ACTIVITY,
            "benchmark_performance": WEIGHT_BENCHMARK_PERF,
            "ecosystem_breadth":   WEIGHT_ECOSYSTEM_BREADTH,
        },
        "summary":     summary,
        "leaderboard": leaderboard,
        "hf_activity": {
            "window_days": WINDOW_DAYS,
            "US":      hf_us,
            "China":   hf_cn,
            "Other":   raw_summary.get("Other", 0),
            "Unknown": raw_summary.get("Unknown", 0),
            "total":   len(all_models),
        },
        "methodology_note": (
            "Three-proxy composite scored as share-of-combined (US + China = 100). "
            "Proxy 1 — Release Activity (35%): HuggingFace Hub 30-day model updates from tracked "
            "labs + estimated ModelScope supplement for Chinese labs with limited HF presence. "
            "Proxy 2 — Benchmark Performance (45%): average of LMSYS Chatbot Arena top-20 Elo "
            "share and Epoch AI notable-model count share (2-year window). Manual snapshot updated "
            "periodically in data/frontier_models_manual.json. "
            "Proxy 3 — Ecosystem Breadth (20%): HF monthly download share (55%) + ModelScope "
            "platform presence estimate (45%). "
            "IMPORTANT: This composite measures open-model activity and public benchmark "
            "performance. It does NOT capture closed-model capability (GPT-4o, Claude, Qwen API, "
            "Doubao) or classified/non-public AI development."
        ),
        "models": all_models,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    comp_us = summary["US"]["composite_score"]
    comp_cn = summary["China"]["composite_score"]
    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("HF activity:   US=%d  China=%d", hf_us, hf_cn)
    log.info("With supplement: US=%d  China=%d", hf_us + supp_us, hf_cn + supp_cn)
    log.info("Composite:     US=%.1f  China=%.1f", comp_us, comp_cn)
    log.info("Score (0-10):  US=%.1f  China=%.1f", comp_us / 10, comp_cn / 10)


if __name__ == "__main__":
    main()
