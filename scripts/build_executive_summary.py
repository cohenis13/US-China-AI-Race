#!/usr/bin/env python3
"""
Build the executive summary JSON from the current dimension data outputs.

Reads data/{frontier_models,talent,compute,adoption,diffusion,energy}.json,
normalizes each dimension to a 0–10 comparative score, then generates
data/executive_summary.json — the single source of truth for the top
executive summary section of the dashboard.

NORMALIZATION
  Count-based dimensions (Frontier Models, Talent, Compute):
    score = clamp(US/(US+China) * 10, 0.5, 9.5)
    china_score = 10.0 – us_score
    (so US + China = 10 by construction; reflects relative share only)

  Composite 0–100 dimensions (Adoption, Energy):
    us_score   = composite_score / 10
    china_score = composite_score / 10
    (independent — do not need to sum to 10)

  Share-of-combined (Diffusion, already US+China=100):
    us_score   = composite_score / 10
    china_score = composite_score / 10
    (sum ≈ 10 by construction of the diffusion index)

CAVEATS BAKED INTO THE METHODOLOGY
  - Compute: TOP500 only. China's exascale systems not submitted to TOP500
    cause China's score to be a significant undercount.
  - Frontier Models: HF Hub activity counts only. China's closed-model
    and domestic-platform capability is broader than this proxy captures.
  - Talent: paper volume proxy, not researcher quality or impact.

This script has no external dependencies — stdlib only (json, pathlib, datetime).
It can be called as the final step of any dimension refresh workflow.

Outputs: data/executive_summary.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
DATA   = ROOT / "data"
OUTPUT = DATA / "executive_summary.json"

# ── Dimension registry ────────────────────────────────────────────────────────
# Order used for the radar chart must match DIMS in index.html:
#   ['Frontier\nModels', 'Compute', 'Adoption', 'Diffusion', 'Energy', 'Talent']
RADAR_ORDER = ["frontier_models", "compute", "adoption", "diffusion", "energy", "talent"]
TABLE_ORDER = ["frontier_models", "compute", "adoption", "diffusion", "energy", "talent"]

DIMS = {
    "frontier_models": {
        "label":       "Frontier Models",
        "radar_label": "Frontier\nModels",
        "confidence":  "Medium confidence",
        "method":      "count_share",
        "caveat":      (
            "Three-proxy composite: release activity on HuggingFace Hub + ModelScope supplement (35%), "
            "benchmark performance via LMSYS Arena and Epoch AI notable models (45%), "
            "and ecosystem breadth across HF and ModelScope platforms (20%). "
            "Does NOT capture closed-model capability (GPT-4o, Claude, Qwen API, Doubao). "
            "China's HF-only activity is a systematic undercount — ModelScope supplement and "
            "ecosystem breadth proxy partially correct for this. "
            "See data/frontier_models_manual.json for benchmark snapshots and methodology notes."
        ),
    },
    "talent": {
        "label":       "Talent",
        "radar_label": "Talent",
        "confidence":  "Medium confidence",
        "method":      "count_share",
        "caveat":      (
            "Three-proxy talent pipeline index: research output quality (35%, OpenAlex "
            "paper volume + high-impact + top-cited), domestic PhD pipeline (25%, NSF SDR "
            "and China MoE annual graduate data), and elite researcher concentration + "
            "migration (40%, MacroPolo AI Talent Tracker). "
            "Paper volume alone overstates China's advantage; adding elite researcher "
            "placement (US captures ~72% of combined US+China top researchers) produces "
            "a near-tie. Key dynamic: China's universities produce 4× more AI-adjacent "
            "PhDs than the US, but the US absorbs a disproportionate share of elite talent "
            "from China and globally. China's domestic retention of top researchers has "
            "increased significantly since 2019."
        ),
    },
    "compute": {
        "label":       "Compute",
        "radar_label": "Compute",
        "confidence":  "Medium confidence",
        "method":      "count_share",
        "caveat":      (
            "Triangulated index: training compute (40%, Epoch AI disclosed FLOPs), "
            "hardware supply (40%, NVIDIA FY2025 10-K geographic revenue + Huawei Ascend "
            "deployment estimates), and visible HPC (20%, TOP500 + China non-submission "
            "corrections + US private clusters). "
            "Systematic gaps remain: China's frontier closed models do not disclose compute; "
            "Huawei Ascend deployment scale relies on analyst estimates; China stopped "
            "submitting most HPC systems to TOP500 after 2023. "
            "A separate hidden-compute uncertainty band (China 20–42% est.) is shown in "
            "the detail panel — the scored composite (25%) is a conservative lower bound."
        ),
    },
    "adoption": {
        "label":       "Adoption",
        "radar_label": "Adoption",
        "confidence":  "Lower confidence",
        "method":      "composite_0_100",
        "caveat":      (
            "Composite of enterprise AI adoption rate and industrial robot density. "
            "China's enterprise figure is estimated from regional data (medium confidence). "
            "Does not capture consumer AI usage, SME adoption, or AI quality/depth."
        ),
    },
    "diffusion": {
        "label":       "Diffusion",
        "radar_label": "Diffusion",
        "confidence":  "Lower confidence",
        "method":      "composite_share_100",
        "caveat":      (
            "Share of combined US+China: HF open-model downloads (55%) + cloud platform "
            "footprint (45%). Undercounts Chinese model reach via ModelScope and domestic "
            "platforms. Does not capture closed-API usage or hardware export reach."
        ),
    },
    "energy": {
        "label":       "Energy",
        "radar_label": "Energy",
        "confidence":  "High confidence",
        "method":      "composite_0_100",
        "caveat":      (
            "Composite of electricity capacity addition rate (40%), data center demand "
            "headroom (35%), and grid connection speed (25%). Measures AI scaling capacity, "
            "not total energy. Does not capture private energy arrangements or nuclear buildout."
        ),
    },
}


# ── Data extraction ───────────────────────────────────────────────────────────
def load_json(key: str) -> dict | None:
    path = DATA / f"{key}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def extract_raw(key: str, data: dict) -> tuple[float | None, float | None]:
    """Return (us_raw, china_raw) for a dimension."""
    s = data.get("summary", {})

    if key == "frontier_models":
        us_val = s.get("US")
        cn_val = s.get("China")
        # Schema v2.0: summary.US is an object with composite_score
        if isinstance(us_val, dict):
            return (us_val.get("composite_score"), cn_val.get("composite_score") if isinstance(cn_val, dict) else None)
        # Legacy schema: summary.US is a raw count integer
        return (float(us_val) if us_val is not None else None,
                float(cn_val) if cn_val is not None else None)

    if key == "talent":
        us_val = s.get("US")
        cn_val = s.get("China")
        # Schema v2.0: composite_score (triangulated index — US+China sums to 100)
        if isinstance(us_val, dict) and us_val.get("composite_score") is not None:
            return (us_val.get("composite_score"),
                    cn_val.get("composite_score") if isinstance(cn_val, dict) else None)
        # Legacy schema: plain integer paper counts
        return (float(us_val) if us_val is not None else None,
                float(cn_val) if cn_val is not None else None)

    if key == "compute":
        us_val = s.get("US")
        cn_val = s.get("China")
        # Schema v2.0: composite_score (triangulated index — US+China sums to 100)
        if isinstance(us_val, dict) and us_val.get("composite_score") is not None:
            return (us_val.get("composite_score"),
                    cn_val.get("composite_score") if isinstance(cn_val, dict) else None)
        # Pre-v2.0: Epoch AI training compute FLOPs
        us_flop = (us_val or {}).get("training_compute_flop")
        cn_flop = (cn_val or {}).get("training_compute_flop")
        if us_flop is not None and cn_flop is not None:
            return float(us_flop), float(cn_flop)
        # Legacy: TOP500 Rmax
        us = (us_val or {}).get("rmax_pflops")
        cn = (cn_val or {}).get("rmax_pflops")
        return (float(us) if us is not None else None,
                float(cn) if cn is not None else None)

    if key in ("adoption", "energy"):
        us = s.get("US", {}).get("composite_score")
        cn = s.get("China", {}).get("composite_score")
        return (float(us) if us is not None else None,
                float(cn) if cn is not None else None)

    if key == "diffusion":
        us = s.get("US", {}).get("composite_score")
        cn = s.get("China", {}).get("composite_score")
        return (float(us) if us is not None else None,
                float(cn) if cn is not None else None)

    return None, None


# ── Normalization ─────────────────────────────────────────────────────────────
def normalize(us_raw: float, cn_raw: float, method: str) -> tuple[float, float]:
    """Normalize raw values to a 0–10 scale."""
    if method == "count_share":
        total = us_raw + cn_raw
        if total <= 0:
            return 5.0, 5.0
        us_share = us_raw / total
        us_score = min(max(round(us_share * 10.0, 1), 0.5), 9.5)
        cn_score = round(10.0 - us_score, 1)
        return us_score, cn_score

    # composite_0_100 and composite_share_100: divide by 10
    us_score = round(us_raw / 10.0, 1)
    cn_score = round(cn_raw / 10.0, 1)
    return us_score, cn_score


# ── Score helpers ─────────────────────────────────────────────────────────────
def edge_info(us: float, cn: float) -> tuple[str, str, float]:
    """Returns (edge_label, winner, delta)."""
    delta = round(abs(us - cn), 1)
    if delta < 0.15:
        return "Parity", "Tie", 0.0
    if us > cn:
        return f"+{delta:.1f} US", "US", delta
    return f"+{delta:.1f} CN", "China", delta


def natural_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + ", and " + items[-1]


# ── Text generation ───────────────────────────────────────────────────────────
def make_current_read(dims: list[dict]) -> str:
    """One-sentence strategic summary of the current competitive picture."""
    # Map dimension IDs to sharper strategic descriptions
    STRATEGIC_LABEL: dict[str, str] = {
        "investment":      "capital",
        "compute":         "compute",
        "frontier_models": "frontier model development",
        "diffusion":       "global deployment",
        "talent":          "research talent",
        "energy":          "energy capacity",
        "adoption":        "domestic adoption",
    }

    us_wins = sorted([d for d in dims if d["winner"] == "US"],    key=lambda x: -x["delta"])
    cn_wins = sorted([d for d in dims if d["winner"] == "China"], key=lambda x: -x["delta"])
    ties    = [d for d in dims if d["winner"] == "Tie"]

    def strategic(d: dict) -> str:
        return STRATEGIC_LABEL.get(d["id"], d["label"].lower())

    clauses = []
    if us_wins:
        clauses.append("The U.S. leads in " + natural_join([strategic(d) for d in us_wins]))
    if cn_wins:
        prefix = "while China leads in" if clauses else "China leads in"
        clauses.append(prefix + " " + natural_join([strategic(d) for d in cn_wins]))
    if ties:
        clauses.append(natural_join([strategic(d) for d in ties]) + " at parity")

    if not clauses:
        return "Insufficient data for current-read summary."
    return ", ".join(clauses) + "."


def make_insights(dims: list[dict]) -> list[dict]:
    """Return 4 strategic insight bullets as {bold, rest} dicts."""
    us_wins = sorted([d for d in dims if d["winner"] == "US"],    key=lambda x: -x["delta"])
    cn_wins = sorted([d for d in dims if d["winner"] == "China"], key=lambda x: -x["delta"])

    insights = []

    # 1. Strongest U.S. advantage
    if us_wins:
        top = us_wins[0]
        others = [d["label"] for d in us_wins[1:]]
        all_us_labels = natural_join([d["label"] for d in us_wins])
        if top["key"] == "compute":
            insights.append({
                "bold": "The U.S. leads on disclosed compute, frontier model activity, and global diffusion",
                "rest": (
                    " — driven by dominant GPU infrastructure, frontier lab concentration, "
                    "and the global reach of US open-source models. Note: Compute score "
                    "reflects TOP500 data only and understates China\u2019s actual capacity."
                ),
            })
        else:
            insights.append({
                "bold": f"The U.S. leads in {all_us_labels}",
                "rest": (
                    f" — the largest U.S. advantage is in {top['label']} "
                    f"(+{top['delta']:.1f} points on the 0\u201310 comparative scale)."
                ),
            })

    # 2. Strongest China advantage
    if cn_wins:
        all_cn_labels = natural_join([d["label"] for d in cn_wins])
        top = cn_wins[0]
        insights.append({
            "bold": f"China leads in {all_cn_labels}",
            "rest": (
                " — particularly in energy infrastructure scaling capacity "
                "and AI research paper volume, where China\u2019s structural advantages "
                f"are most pronounced (+{top['delta']:.1f} points in {top['label']})."
            ),
        })

    # 3. Most contested dimension
    if dims:
        closest = min(dims, key=lambda x: x["delta"])
        insights.append({
            "bold": f"{closest['label']} is the most closely contested dimension",
            "rest": (
                f" on these proxies (gap: {closest['delta']:.1f} points on the 0\u201310 scale) "
                "\u2014 both countries are operating at broadly comparable levels here."
            ),
        })

    # 4. Binding constraints
    has_compute = any(d["key"] == "compute" for d in dims)
    has_energy  = any(d["key"] == "energy"  for d in dims)
    if has_compute and has_energy:
        insights.append({
            "bold": "The binding constraints differ structurally",
            "rest": (
                ": export controls on advanced chips are China\u2019s most salient bottleneck; "
                "grid interconnection delays and power permitting are the most acute constraint "
                "on continued U.S. AI data center expansion."
            ),
        })

    return insights


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now = datetime.now(timezone.utc)

    scored: list[dict] = []
    missing: list[str] = []

    for key, cfg in DIMS.items():
        raw_data = load_json(key)
        if raw_data is None:
            missing.append(key)
            continue

        us_raw, cn_raw = extract_raw(key, raw_data)
        if us_raw is None or cn_raw is None:
            missing.append(key)
            continue

        us_score, cn_score = normalize(us_raw, cn_raw, cfg["method"])
        edge, winner, delta = edge_info(us_score, cn_score)

        scored.append({
            "key":          key,
            "label":        cfg["label"],
            "radar_label":  cfg["radar_label"],
            "us_score":     us_score,
            "china_score":  cn_score,
            "winner":       winner,
            "delta":        delta,
            "edge":         edge,
            "confidence":   cfg["confidence"],
            "score_method": cfg["method"],
            "caveat":       cfg["caveat"],
            "source_file":  f"data/{key}.json",
        })

    # Build radar arrays (must match RADAR_ORDER = DIMS in index.html)
    by_key = {d["key"]: d for d in scored}
    radar_us = [by_key[k]["us_score"]    if k in by_key else None for k in RADAR_ORDER]
    radar_cn = [by_key[k]["china_score"] if k in by_key else None for k in RADAR_ORDER]

    # Score table rows
    table_rows = [
        {
            "key":       d["key"],
            "dimension": d["label"],
            "us":        d["us_score"],
            "china":     d["china_score"],
            "winner":    d["winner"],
            "delta":     d["delta"],
            "edge":      d["edge"],
        }
        for k in TABLE_ORDER
        if (d := by_key.get(k)) is not None
    ]

    current_read = make_current_read(scored)
    insights     = make_insights(scored)

    output = {
        "fetched_at":         now.isoformat(),
        "generated_from":     [d["key"] for d in scored],
        "missing_dimensions": missing,
        "dimensions":         scored,
        "current_read":       current_read,
        "strategic_insights": insights,
        "score_table":        table_rows,
        "radar_chart_data": {
            "order":  RADAR_ORDER,
            "us":     radar_us,
            "china":  radar_cn,
        },
        "normalization_note": (
            "Frontier Models, Talent, and Compute are scored as share-of-combined "
            "(US\u2009+\u2009China\u2009=\u200910 by construction). "
            "Adoption, Diffusion, and Energy use their 0\u2013100 composite scores "
            "divided by 10, giving independent scores that do not necessarily sum to 10."
        ),
        "confidence_note": (
            "Compute score is a triangulated lower bound — China's true compute share "
            "is likely 25\u201340% (see hidden_compute_band in data/compute.json). "
            "Frontier Models score reflects the open model ecosystem (HF + ModelScope); "
            "closed-model capability not captured. "
            "See dimension caveats and docs/methodology.html for full details."
        ),
    }

    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"Wrote {OUTPUT}")
    for d in scored:
        print(f"  {d['label']:<22}  US={d['us_score']:4.1f}  "
              f"China={d['china_score']:4.1f}  Winner={d['winner']}  delta={d['delta']}")
    if missing:
        print(f"  Missing/skipped: {missing}")
    print(f"\nCurrent read: {current_read}")


if __name__ == "__main__":
    main()
