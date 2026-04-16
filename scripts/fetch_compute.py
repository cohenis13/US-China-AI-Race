#!/usr/bin/env python3
"""
Fetch compute data and build the triangulated compute index.

THREE PROXIES
  1. Training Compute (weight 0.40) — Epoch AI "Notable AI Models" CSV
     Cumulative AI training FLOPs for models since 2023 with known compute.
     Directly measures the compute actually used to train frontier models.
     Understates China: closed models (Qwen-max, Doubao) do not disclose compute.

  2. Hardware Supply (weight 0.40) — NVIDIA geographic revenue + Huawei Ascend
     Manually maintained in data/compute_manual.json. Measures the flow of
     AI compute hardware to each country. Updates when new NVIDIA 10-Ks or
     Huawei announcements are available.

  3. Visible HPC (weight 0.20) — TOP500 + China non-submission correction
     TOP500 alone severely understates China (stopped submitting 2023+).
     Manual corrections from data/compute_manual.json are applied.

COMPOSITE
  share_score = proxy_us / (proxy_us + proxy_cn) × 100
  composite   = sum(weight_i × share_score_i)
  US + China composite always sums to 100 by construction.

COVERAGE NOTE
  A separate hidden_compute_band (from compute_manual.json) is included in
  the output but NOT used in scoring — it represents the uncertainty range
  for total (visible + estimated hidden) compute.

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
ROOT         = Path(__file__).resolve().parent.parent
OUTPUT_FILE  = ROOT / "data" / "compute.json"
MANUAL_FILE  = ROOT / "data" / "compute_manual.json"

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_TRAINING_COMPUTE = 0.40
WEIGHT_HARDWARE_SUPPLY  = 0.40
WEIGHT_VISIBLE_HPC      = 0.20

# ── Epoch AI config ───────────────────────────────────────────────────────────
EPOCH_CSV_URL     = "https://epoch.ai/data/all_ai_models.csv"
EPOCH_CUTOFF_DATE = "2023-01-01"
EPOCH_MIN_FLOP    = 1e20
EPOCH_TOP_N       = 10

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
#  Manual data
# ══════════════════════════════════════════════════════════════════════════════

def load_manual_data() -> dict:
    if not MANUAL_FILE.exists():
        log.error("compute_manual.json not found at %s", MANUAL_FILE)
        sys.exit(1)
    with open(MANUAL_FILE, encoding="utf-8") as f:
        data = json.load(f)
    log.info("Loaded compute_manual.json (last_updated: %s)", data.get("last_updated", "?"))
    return data


# ══════════════════════════════════════════════════════════════════════════════
#  EPOCH AI — training compute
# ══════════════════════════════════════════════════════════════════════════════

def fetch_epoch_csv() -> str | None:
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
    raw = (raw or "").strip()
    for fragment, bucket in EPOCH_COUNTRY_MAP.items():
        if fragment in raw:
            return bucket
    return "Other"


def parse_epoch_csv(text: str) -> list[dict]:
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
            "name":                  name,
            "organization":          org,
            "country":               classify_epoch_country(country_r),
            "country_raw":           country_r,
            "publication_date":      date_str,
            "training_compute_flop": flop,
        })

    log.info(
        "Epoch AI parsed: %d models kept | skipped: %d no-compute, %d pre-%s, %d too-small",
        len(models), skipped_no_compute, skipped_old,
        EPOCH_CUTOFF_DATE[:4], skipped_small,
    )
    return models


def aggregate_epoch(models: list[dict]) -> dict:
    buckets: dict[str, dict] = {
        "US":    {"model_count": 0, "training_compute_flop": 0.0},
        "China": {"model_count": 0, "training_compute_flop": 0.0},
        "Other": {"model_count": 0, "training_compute_flop": 0.0},
    }
    for m in models:
        b = m["country"] if m["country"] in buckets else "Other"
        buckets[b]["model_count"]           += 1
        buckets[b]["training_compute_flop"] += m["training_compute_flop"]
    for b in buckets.values():
        b["training_compute_flop"] = float(f"{b['training_compute_flop']:.6e}")
    return buckets


def top_models_by_compute(models: list[dict], n: int) -> list[dict]:
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
#  Composite builder
# ══════════════════════════════════════════════════════════════════════════════

def build_compute_composite(
    epoch_us_flop: float | None,
    epoch_cn_flop: float | None,
    epoch_us_models: int,
    epoch_cn_models: int,
    top500_us_rmax: float,
    top500_cn_rmax: float,
    manual: dict,
) -> dict:
    """
    Build the triangulated compute index from 3 proxies.
    Returns a summary dict with composite_score and per-proxy breakdown.
    """

    # ── Proxy 1: Training compute ─────────────────────────────────────────────
    if epoch_us_flop is not None and epoch_cn_flop is not None:
        epoch_total = epoch_us_flop + epoch_cn_flop
        tc_us = round(epoch_us_flop / epoch_total * 100, 1) if epoch_total > 0 else 50.0
        tc_cn = round(100.0 - tc_us, 1)
        tc_source = "Epoch AI notable models since 2023 — disclosed training compute only"
        tc_coverage = (
            "Understates China: frontier closed models (Qwen-max, Doubao, Hunyuan) "
            "do not disclose compute. Disclosed compute is a lower bound for China."
        )
    else:
        log.warning("Epoch AI data unavailable — using seeded training compute shares")
        tc_us, tc_cn = 85.1, 14.9
        epoch_us_flop = epoch_cn_flop = None
        tc_source = "Seeded — Epoch AI unavailable at last fetch"
        tc_coverage = "Seeded values; re-run script when Epoch AI is accessible."

    # ── Proxy 2: Hardware supply ──────────────────────────────────────────────
    hs = manual.get("hardware_supply", {})
    hs_totals = hs.get("adjusted_totals", {})
    hw_us = hs_totals.get("us_share_pct", 68.0)
    hw_cn = hs_totals.get("china_share_pct", 32.0)
    nv = hs.get("nvidia_geographic_revenue", {})
    asc = hs.get("huawei_ascend_adjustment", {})

    # ── Proxy 3: Visible HPC ──────────────────────────────────────────────────
    hpc = manual.get("hpc_capacity", {})
    hpc_totals = hpc.get("adjusted_totals", {})
    # Use fresh TOP500 data if available, otherwise fall back to manual seeds
    if top500_us_rmax > 0:
        us_priv = hpc.get("us_private_clusters", {}).get("total_estimated_additional_hpl_rmax_pflops", 2300)
        cn_corr = hpc.get("china_non_top500_systems", {}).get("total_estimated_additional_hpl_rmax_pflops", 3300)
        adj_us  = round(top500_us_rmax + us_priv, 1)
        adj_cn  = round(top500_cn_rmax + cn_corr, 1)
    else:
        adj_us = hpc_totals.get("us_adjusted_pflops", 9261.3)
        adj_cn = hpc_totals.get("china_adjusted_pflops", 3505.0)
        us_priv = hpc_totals.get("us_private_addition_pflops", 2300)
        cn_corr = hpc_totals.get("china_correction_pflops", 3300)

    hpc_total = adj_us + adj_cn
    hpc_us = round(adj_us / hpc_total * 100, 1) if hpc_total > 0 else 72.5
    hpc_cn = round(100.0 - hpc_us, 1)

    # ── Composite ─────────────────────────────────────────────────────────────
    comp_us = round(
        WEIGHT_TRAINING_COMPUTE * tc_us +
        WEIGHT_HARDWARE_SUPPLY  * hw_us +
        WEIGHT_VISIBLE_HPC      * hpc_us,
        1,
    )
    comp_cn = round(100.0 - comp_us, 1)

    log.info("Compute composite: US=%.1f%% China=%.1f%%", comp_us, comp_cn)
    log.info("  Training compute (40%%): US=%.1f%% China=%.1f%%", tc_us, tc_cn)
    log.info("  Hardware supply  (40%%): US=%.1f%% China=%.1f%%", hw_us, hw_cn)
    log.info("  Visible HPC      (20%%): US=%.1f%% China=%.1f%%", hpc_us, hpc_cn)

    hidden = manual.get("hidden_compute_estimate", {})
    hidden_cn = hidden.get("china_true_share_estimate", {})
    hidden_us = hidden.get("us_true_share_estimate", {})

    return {
        "US": {
            "composite_score": comp_us,
            "proxies": {
                "training_compute": {
                    "weight": WEIGHT_TRAINING_COMPUTE,
                    "share_score": tc_us,
                    "raw_flop": epoch_us_flop,
                    "model_count": epoch_us_models,
                    "source": tc_source,
                    "coverage_note": tc_coverage,
                },
                "hardware_supply": {
                    "weight": WEIGHT_HARDWARE_SUPPLY,
                    "share_score": hw_us,
                    "nvidia_revenue_usd_b": nv.get("us_dc_revenue_usd_b"),
                    "ascend_equivalent_usd_b": None,
                    "source": hs.get("description", "NVIDIA 10-K + Huawei Ascend analyst estimates"),
                    "confidence": hs.get("huawei_ascend_adjustment", {}).get("confidence", "Low-Medium"),
                },
                "visible_hpc": {
                    "weight": WEIGHT_VISIBLE_HPC,
                    "share_score": hpc_us,
                    "top500_rmax_pflops": top500_us_rmax,
                    "private_cluster_addition_pflops": us_priv,
                    "adjusted_pflops": adj_us,
                    "source": "TOP500 + private cluster estimates (xAI, Meta, Microsoft)",
                },
            },
        },
        "China": {
            "composite_score": comp_cn,
            "proxies": {
                "training_compute": {
                    "weight": WEIGHT_TRAINING_COMPUTE,
                    "share_score": tc_cn,
                    "raw_flop": epoch_cn_flop,
                    "model_count": epoch_cn_models,
                    "source": tc_source,
                    "coverage_note": tc_coverage,
                },
                "hardware_supply": {
                    "weight": WEIGHT_HARDWARE_SUPPLY,
                    "share_score": hw_cn,
                    "nvidia_revenue_usd_b": nv.get("china_dc_revenue_usd_b"),
                    "ascend_equivalent_usd_b": asc.get("estimated_value_usd_b"),
                    "source": hs.get("description", "NVIDIA 10-K + Huawei Ascend analyst estimates"),
                    "confidence": asc.get("confidence", "Low"),
                },
                "visible_hpc": {
                    "weight": WEIGHT_VISIBLE_HPC,
                    "share_score": hpc_cn,
                    "top500_rmax_pflops": top500_cn_rmax,
                    "non_top500_correction_pflops": cn_corr,
                    "adjusted_pflops": adj_cn,
                    "source": "TOP500 + China non-submission corrections (Tianhe-3, Sunway NG, etc.)",
                },
            },
        },
        "hidden_compute_band": {
            "description": hidden.get("description", ""),
            "confidence": hidden.get("confidence", "Low"),
            "china_lower_pct": hidden_cn.get("lower_bound_pct", 20),
            "china_point_pct": hidden_cn.get("point_estimate_pct", 30),
            "china_upper_pct": hidden_cn.get("upper_bound_pct", 42),
            "us_lower_pct": hidden_us.get("lower_bound_pct", 58),
            "us_point_pct": hidden_us.get("point_estimate_pct", 70),
            "us_upper_pct": hidden_us.get("upper_bound_pct", 80),
            "narrative": hidden_cn.get("narrative", ""),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    manual = load_manual_data()

    # ── Epoch AI ─────────────────────────────────────────────────────────────
    epoch_ok = False
    epoch_summary: dict = {}
    epoch_top_models: list[dict] = []

    epoch_text = fetch_epoch_csv()
    if epoch_text:
        models = parse_epoch_csv(epoch_text)
        if models:
            epoch_summary    = aggregate_epoch(models)
            epoch_top_models = top_models_by_compute(models, EPOCH_TOP_N)
            epoch_ok = True
        else:
            log.warning("Epoch AI: parsed 0 qualifying models")
    else:
        log.warning("Epoch AI fetch failed — will use seeded training compute shares")

    epoch_us_flop   = epoch_summary.get("US", {}).get("training_compute_flop") if epoch_ok else None
    epoch_cn_flop   = epoch_summary.get("China", {}).get("training_compute_flop") if epoch_ok else None
    epoch_us_models = epoch_summary.get("US", {}).get("model_count", 0) if epoch_ok else 0
    epoch_cn_models = epoch_summary.get("China", {}).get("model_count", 0) if epoch_ok else 0

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
        else:
            log.warning("TOP500: only %d systems parsed — skipping", len(systems))
    else:
        log.warning("TOP500 fetch failed — will use manual HPC seeds")

    top500_us_rmax = top500_summary.get("US", {}).get("rmax_pflops", 0.0) if top500_ok else 0.0
    top500_cn_rmax = top500_summary.get("China", {}).get("rmax_pflops", 0.0) if top500_ok else 0.0

    if not epoch_ok and not top500_ok:
        log.warning("Both live sources failed — building composite from manual seeds only")

    # ── Build composite ───────────────────────────────────────────────────────
    composite = build_compute_composite(
        epoch_us_flop, epoch_cn_flop,
        epoch_us_models, epoch_cn_models,
        top500_us_rmax, top500_cn_rmax,
        manual,
    )

    output = {
        "schema_version": "2.0",
        "dimension":      "compute",
        "metric_key":     "compute_triangulated_index",
        "description": (
            "Triangulated compute index: training compute (40%, Epoch AI), "
            "hardware supply (40%, NVIDIA revenue + Huawei Ascend), and "
            "visible HPC (20%, TOP500 + corrections). "
            "Coverage gaps are explicitly documented in hidden_compute_band."
        ),
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "weights": {
            "training_compute": WEIGHT_TRAINING_COMPUTE,
            "hardware_supply":  WEIGHT_HARDWARE_SUPPLY,
            "visible_hpc":      WEIGHT_VISIBLE_HPC,
        },
        "summary": {
            "US":    composite["US"],
            "China": composite["China"],
        },
        "hidden_compute_band": composite["hidden_compute_band"],
        "epoch_ai": {
            "source_url":            EPOCH_CSV_URL,
            "cutoff_date":           EPOCH_CUTOFF_DATE,
            "min_flop":              EPOCH_MIN_FLOP,
            "data_available":        epoch_ok,
            "top_models_by_compute": epoch_top_models,
            "methodology": (
                f"Sums training_compute_flop for models published on/after {EPOCH_CUTOFF_DATE} "
                f"with known compute >= {EPOCH_MIN_FLOP:.0e} FLOPs. Country by 'Country (of "
                "organization)'. Models without compute estimates are excluded — this "
                "understates totals for both countries, more so for China where "
                "frontier closed models do not disclose compute."
            ),
        },
        "top500": {
            "source_url":    TOP500_BASE,
            "list_edition":  top500_edition,
            "data_available": top500_ok,
            "total_systems": sum(v["systems"] for v in top500_summary.values()) if top500_ok else 0,
            "summary":       top500_summary if top500_ok else {},
            "top_systems":   top500_systems,
            "china_non_submission_note": manual.get("hpc_capacity", {}).get("top500_coverage_warning", ""),
        },
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("Triangulated compute composite:")
    log.info("  US:    %.1f%%  (score ≈ %.1f/10)",
             composite["US"]["composite_score"],
             composite["US"]["composite_score"] / 10)
    log.info("  China: %.1f%%  (score ≈ %.1f/10)",
             composite["China"]["composite_score"],
             composite["China"]["composite_score"] / 10)


if __name__ == "__main__":
    main()
