#!/usr/bin/env python3
"""
Fetch compute data from two complementary sources:

PRIMARY  — Epoch AI "Notable AI Models" CSV
  Cumulative AI training compute (FLOPs) attributed to US vs China labs,
  for models published since 2023 with known training compute.
  This directly measures the compute actually used to build frontier AI.
  Both US and China labs (DeepSeek, Qwen, etc.) are tracked.
  URL: https://epoch.ai/data/all_ai_models.csv

SECONDARY — TOP500 supercomputer list (XML)
  Aggregate HPL Rmax benchmark performance, grouped by country.
  Kept as a transparency/reference metric only — China stopped submitting
  most systems in 2023, so this significantly understates China's real
  HPC capacity and is no longer suitable as a primary score driver.
  URL: https://www.top500.org/lists/top500/

The compute score written to data/compute.json is driven by
the Epoch AI training-compute share. TOP500 figures are retained
as supplementary context in the same file.

Outputs to data/compute.json.

Usage:
    pip install requests
    python scripts/fetch_compute.py
"""

import csv
import io
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
OUTPUT_FILE = ROOT / "data" / "compute.json"

# ── Epoch AI config ───────────────────────────────────────────────────────────
EPOCH_CSV_URL     = "https://epoch.ai/data/all_ai_models.csv"
EPOCH_CUTOFF_DATE = "2023-01-01"   # only count models published on/after this date
EPOCH_MIN_FLOP    = 1e20           # ignore models smaller than this (toys / fine-tunes)
EPOCH_TOP_N       = 10             # top models by compute to surface in output

# Country strings in the "Country (of organization)" column → summary bucket
EPOCH_COUNTRY_MAP = {
    "United States": "US",
    "China":         "China",
}

# ── TOP500 config ─────────────────────────────────────────────────────────────
TOP500_BASE        = "https://www.top500.org"
TOP500_LISTS_URL   = f"{TOP500_BASE}/lists/top500/"
TOP500_FALLBACK_Y  = 2025
TOP500_FALLBACK_M  = 11
TOP500_TIMEOUT     = 60
TOP500_MAX_OUT     = 20
MIN_SYSTEMS        = 400

HEADERS = {
    "User-Agent": "us-china-ai-tracker/1.0 (public research dashboard)",
    "Accept":     "*/*",
}


# ══════════════════════════════════════════════════════════════════════════════
#  EPOCH AI — training compute
# ══════════════════════════════════════════════════════════════════════════════

def fetch_epoch_csv() -> str | None:
    """Download the Epoch AI all_ai_models CSV. Returns raw text or None."""
    log.info("Fetching Epoch AI CSV: %s", EPOCH_CSV_URL)
    try:
        resp = requests.get(EPOCH_CSV_URL, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        log.info("Epoch AI CSV: %d bytes", len(resp.content))
        return resp.text
    except requests.exceptions.RequestException as e:
        log.error("Epoch AI fetch failed: %s", e)
        return None


def classify_epoch_country(raw: str) -> str:
    """Map Epoch AI country string to US / China / Other."""
    raw = (raw or "").strip()
    for fragment, bucket in EPOCH_COUNTRY_MAP.items():
        if fragment in raw:
            return bucket
    return "Other"


def parse_epoch_csv(text: str) -> list[dict]:
    """
    Parse the Epoch AI CSV and return a flat list of model dicts with fields:
        name, organization, country, publication_date, training_compute_flop
    Only models passing the cutoff and min-FLOP filter are returned.
    """
    reader = csv.DictReader(io.StringIO(text))
    models = []
    skipped_no_compute = 0
    skipped_old        = 0
    skipped_small      = 0

    for row in reader:
        name      = (row.get("Model")                      or "").strip()
        org       = (row.get("Organization")               or "").strip()
        country_r = (row.get("Country (of organization)")  or "").strip()
        flop_str  = (row.get("Training compute (FLOP)")    or "").strip()
        date_str  = (row.get("Publication date")           or "").strip()

        if not flop_str:
            skipped_no_compute += 1
            continue

        # Date filter
        if not date_str or date_str < EPOCH_CUTOFF_DATE:
            skipped_old += 1
            continue

        try:
            flop = float(flop_str)
        except ValueError:
            skipped_no_compute += 1
            continue

        if flop < EPOCH_MIN_FLOP:
            skipped_small += 1
            continue

        models.append({
            "name":                   name,
            "organization":           org,
            "country":                classify_epoch_country(country_r),
            "country_raw":            country_r,
            "publication_date":       date_str,
            "training_compute_flop":  flop,
        })

    log.info(
        "Epoch AI parsed: %d models kept | skipped: %d no-compute, %d pre-%s, %d too-small",
        len(models), skipped_no_compute, skipped_old,
        EPOCH_CUTOFF_DATE[:4], skipped_small,
    )
    return models


def aggregate_epoch(models: list[dict]) -> dict:
    """
    Aggregate training compute and model counts by country bucket.
    Returns a dict: { "US": {...}, "China": {...}, "Other": {...} }
    """
    buckets: dict[str, dict] = {
        "US":    {"model_count": 0, "training_compute_flop": 0.0},
        "China": {"model_count": 0, "training_compute_flop": 0.0},
        "Other": {"model_count": 0, "training_compute_flop": 0.0},
    }
    for m in models:
        b = m["country"]
        if b not in buckets:
            b = "Other"
        buckets[b]["model_count"]           += 1
        buckets[b]["training_compute_flop"] += m["training_compute_flop"]

    # Round for cleaner JSON
    for b in buckets.values():
        b["training_compute_flop"] = float(f"{b['training_compute_flop']:.6e}")

    return buckets


def top_models_by_compute(models: list[dict], n: int) -> list[dict]:
    """Return the n models with the highest training compute."""
    sorted_m = sorted(models, key=lambda m: m["training_compute_flop"], reverse=True)
    return [
        {
            "rank":                  i + 1,
            "name":                  m["name"],
            "organization":          m["organization"],
            "country":               m["country"],
            "publication_date":      m["publication_date"],
            "training_compute_flop": m["training_compute_flop"],
        }
        for i, m in enumerate(sorted_m[:n])
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  TOP500 — supplementary HPC data
# ══════════════════════════════════════════════════════════════════════════════

def get_top500_edition() -> tuple[int, int]:
    try:
        resp = requests.get(TOP500_LISTS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        pattern = re.compile(r"/lists/top500/(\d{4})/(\d{2})/?")
        candidates = [(int(m.group(1)), int(m.group(2)))
                      for m in pattern.finditer(resp.text)]
        if candidates:
            year, month = sorted(candidates, reverse=True)[0]
            log.info("TOP500 latest edition: %d/%02d", year, month)
            return year, month
    except Exception as e:
        log.warning("TOP500 edition detection failed: %s", e)
    log.info("TOP500 fallback edition: %d/%02d", TOP500_FALLBACK_Y, TOP500_FALLBACK_M)
    return TOP500_FALLBACK_Y, TOP500_FALLBACK_M


def download_top500_xml(year: int, month: int) -> bytes | None:
    ym  = f"{year:04d}{month:02d}"
    url = (f"{TOP500_BASE}/lists/top500/{year:04d}/{month:02d}"
           f"/download/TOP500_{ym}_all.xml")
    log.info("Downloading TOP500 XML: %s", url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TOP500_TIMEOUT, stream=True)
        resp.raise_for_status()
        if "html" in resp.headers.get("content-type", ""):
            log.error("TOP500: server returned HTML — download may need auth")
            return None
        data = resp.content
        log.info("TOP500 XML: %d bytes", len(data))
        return data
    except requests.exceptions.RequestException as e:
        log.error("TOP500 XML download failed: %s", e)
        return None


def parse_top500_xml(content: bytes) -> list[dict]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        log.error("TOP500 XML parse error: %s", e)
        return []

    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    def txt(elem: ET.Element, *tags: str) -> str:
        for tag in tags:
            sub = elem.find(tag)
            if sub is not None and sub.text:
                return sub.text.strip()
        return ""

    def iter_entries(parent: ET.Element, depth: int = 0):
        for child in parent:
            if child.find("rank") is not None:
                yield child
            elif depth < 2:
                yield from iter_entries(child, depth + 1)

    top500_country = {"United States": "US", "China": "China"}
    systems = []
    for entry in iter_entries(root):
        rank_str = txt(entry, "rank")
        try:
            rank = int(rank_str)
        except ValueError:
            continue
        name    = txt(entry, "system-name", "systemname", "name", "description")
        country_raw = txt(entry, "country")
        country = top500_country.get(country_raw, "Other")
        rmax_str = txt(entry, "r-max", "rmax", "rmax-gf", "rmax-tf")
        try:
            rmax_pflops = round(float(rmax_str.replace(",", "")) / 1_000_000, 2)
        except (ValueError, AttributeError):
            rmax_pflops = 0.0
        systems.append({
            "rank": rank, "name": name,
            "country": country, "rmax_pflops": rmax_pflops,
        })

    return sorted(systems, key=lambda x: x["rank"])


def aggregate_top500(systems: list[dict]) -> dict:
    buckets = {
        "US":      {"systems": 0, "rmax_pflops": 0.0},
        "China":   {"systems": 0, "rmax_pflops": 0.0},
        "Other":   {"systems": 0, "rmax_pflops": 0.0},
        "Unknown": {"systems": 0, "rmax_pflops": 0.0},
    }
    for s in systems:
        b = s["country"] if s["country"] in buckets else "Unknown"
        buckets[b]["systems"]     += 1
        buckets[b]["rmax_pflops"]  = round(buckets[b]["rmax_pflops"] + s["rmax_pflops"], 2)
    for b in buckets.values():
        b["rmax_pflops"] = round(b["rmax_pflops"], 1)
    return buckets


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:

    # ── Epoch AI ─────────────────────────────────────────────────────────────
    epoch_ok = False
    epoch_summary: dict = {}
    epoch_top_models: list[dict] = []

    epoch_text = fetch_epoch_csv()
    if epoch_text:
        models = parse_epoch_csv(epoch_text)
        if models:
            epoch_summary   = aggregate_epoch(models)
            epoch_top_models = top_models_by_compute(models, EPOCH_TOP_N)
            epoch_ok = True
            us_e  = epoch_summary["US"]
            cn_e  = epoch_summary["China"]
            total = us_e["training_compute_flop"] + cn_e["training_compute_flop"]
            log.info("Epoch AI aggregate (since %s):", EPOCH_CUTOFF_DATE)
            log.info("  US:    %d models, %.3e FLOPs (%.1f%%)",
                     us_e["model_count"], us_e["training_compute_flop"],
                     us_e["training_compute_flop"] / total * 100 if total else 0)
            log.info("  China: %d models, %.3e FLOPs (%.1f%%)",
                     cn_e["model_count"], cn_e["training_compute_flop"],
                     cn_e["training_compute_flop"] / total * 100 if total else 0)
        else:
            log.warning("Epoch AI: parsed 0 qualifying models")
    else:
        log.warning("Epoch AI fetch failed — will rely on TOP500 fallback")

    # ── TOP500 ────────────────────────────────────────────────────────────────
    top500_ok = False
    top500_summary: dict = {}
    top500_systems: list[dict] = []
    top500_edition = ""

    year, month = get_top500_edition()
    top500_edition = f"{year:04d}/{month:02d}"
    xml_content = download_top500_xml(year, month)

    if xml_content:
        systems = parse_top500_xml(xml_content)
        log.info("TOP500: parsed %d systems", len(systems))
        if len(systems) >= MIN_SYSTEMS:
            top500_summary = aggregate_top500(systems)
            top500_systems = [
                {"rank": s["rank"], "name": s["name"],
                 "country": s["country"], "rmax_pflops": s["rmax_pflops"]}
                for s in systems[:TOP500_MAX_OUT]
            ]
            top500_ok = True
            log.info("  US:    %d systems, %.1f PFlops",
                     top500_summary["US"]["systems"],
                     top500_summary["US"]["rmax_pflops"])
            log.info("  China: %d systems, %.1f PFlops",
                     top500_summary["China"]["systems"],
                     top500_summary["China"]["rmax_pflops"])
        else:
            log.warning("TOP500: only %d systems parsed — skipping", len(systems))
    else:
        log.warning("TOP500 fetch failed")

    if not epoch_ok and not top500_ok:
        log.error("Both data sources failed — aborting")
        sys.exit(1)

    # ── Build summary ─────────────────────────────────────────────────────────
    # Primary score field is training_compute_flop (Epoch AI).
    # If Epoch AI failed, fall back to top500 rmax as a last resort.
    def build_country_summary(country: str) -> dict:
        d: dict = {}
        if epoch_ok and country in epoch_summary:
            e = epoch_summary[country]
            d["training_compute_flop"] = e["training_compute_flop"]
            d["model_count"]           = e["model_count"]
        if top500_ok and country in top500_summary:
            t = top500_summary[country]
            d["top500_systems"]     = t["systems"]
            d["top500_rmax_pflops"] = t["rmax_pflops"]
        return d

    summary = {
        "US":    build_country_summary("US"),
        "China": build_country_summary("China"),
    }

    output = {
        "dimension":   "compute",
        "metric_key":  "ai_training_compute",
        "description": (
            "Primary: cumulative AI training compute (FLOPs) for notable models "
            f"published since {EPOCH_CUTOFF_DATE}, grouped by country of the developing "
            "organisation (Epoch AI). Secondary: TOP500 HPL Rmax benchmark performance "
            "(supplementary context only — China stopped submitting most systems in 2023)."
        ),
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "summary":     summary,
        "epoch_ai": {
            "source_url":      EPOCH_CSV_URL,
            "cutoff_date":     EPOCH_CUTOFF_DATE,
            "min_flop":        EPOCH_MIN_FLOP,
            "data_available":  epoch_ok,
            "top_models_by_compute": epoch_top_models,
            "methodology": (
                "Sums training_compute_flop from the Epoch AI all_ai_models CSV for "
                f"models published on/after {EPOCH_CUTOFF_DATE} with known compute >= "
                f"{EPOCH_MIN_FLOP:.0e} FLOPs. Country is determined by 'Country (of "
                "organization)'. Models with no compute estimate are excluded — this "
                "understates totals for both countries but more so for China, where "
                "frontier models (Qwen-max, Doubao, etc.) often do not disclose compute."
            ),
        },
        "top500": {
            "source_url":        TOP500_BASE,
            "list_edition":      top500_edition,
            "data_available":    top500_ok,
            "total_systems":     sum(v["systems"] for v in top500_summary.values()) if top500_ok else 0,
            "is_complete":       top500_ok and sum(v["systems"] for v in top500_summary.values()) >= MIN_SYSTEMS,
            "summary":           top500_summary if top500_ok else {},
            "top_systems":       top500_systems,
            "methodology": (
                "Aggregate HPL Rmax (PFlop/s) from the full TOP500 XML download. "
                "China stopped submitting most exascale-class systems after 2023, "
                "so China's total significantly understates actual capacity. "
                "US private AI clusters (xAI Colossus, Meta AI, etc.) are also "
                "excluded. Retained for transparency and historical comparison only."
            ),
        },
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("Primary metric (Epoch AI training compute):")
    if epoch_ok:
        us_f  = summary["US"].get("training_compute_flop", 0)
        cn_f  = summary["China"].get("training_compute_flop", 0)
        total = us_f + cn_f
        log.info("  US share:    %.1f%%  (%s models)",
                 us_f / total * 100 if total else 0,
                 summary["US"].get("model_count", "?"))
        log.info("  China share: %.1f%%  (%s models)",
                 cn_f / total * 100 if total else 0,
                 summary["China"].get("model_count", "?"))
    else:
        log.info("  (Epoch AI unavailable — using TOP500 fallback)")


if __name__ == "__main__":
    main()
