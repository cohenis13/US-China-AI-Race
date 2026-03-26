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
            "Reflects 30-day model update activity on Hugging Face Hub — a proxy for "
            "lab output velocity, not a definitive capability ranking. China's frontier "
            "capability (DeepSeek R1, Qwen series) is broader than HF Hub counts alone "
            "capture. Counts reflect only US- and China-attributed labs in data/labs.json."
        ),
    },
    "talent": {
        "label":       "Talent",
        "radar_label": "Talent",
        "confidence":  "Medium confidence",
        "method":      "composite_share_100",
        "caveat":      (
            "Three-proxy composite: paper volume (30%), quality papers cited ≥25 "
            "times over 2 years (40%), and high-impact papers cited ≥100 "
            "times over 3 years (30%). Each proxy is the US share of combined "
            "US+China output. China leads on raw volume; the US leads on citation "
            "impact. No venue filter — citation thresholds are a more robust quality "
            "proxy. OpenAlex may undercount Chinese domestic venues not indexed internationally."
        ),
    },
    "compute": {
        "label":       "Compute",
        "radar_label": "Compute",
        "confidence":  "High confidence (TOP500 only)",
        "method":      "count_share",
        "caveat":      (
            "TOP500 list data only. China operates multiple exascale-class systems that "
            "have NOT been submitted to TOP500 — this score significantly understates "
            "China's actual HPC capacity. US private AI cluster infrastructure (xAI "
            "Colossus, Meta clusters, etc.) is also excluded."
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
        us = s.get("US")
        cn = s.get("China")
        return (float(us) if us is not None else None,
                float(cn) if cn is not None else None)

    if key == "talent":
        us = s.get("US", {}).get("composite_score")
        cn = s.get("China", {}).get("composite_score")
        return (float(us) if us is not None else None,
                float(cn) if cn is not None else None)

    if key == "compute":
        us = s.get("US", {}).get("rmax_pflops")
        cn = s.get("China", {}).get("rmax_pflops")
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
    """One-sentence summary of the current competitive picture."""
    us_wins  = sorted([d for d in dims if d["winner"] == "US"],    key=lambda x: -x["delta"])
    cn_wins  = sorted([d for d in dims if d["winner"] == "China"], key=lambda x: -x["delta"])
    ties     = [d for d in dims if d["winner"] == "Tie"]

    parts = []
    if us_wins:
        parts.append("U.S. leads in " + natural_join([d["label"] for d in us_wins]))
    if cn_wins:
        parts.append("China leads in " + natural_join([d["label"] for d in cn_wins]))
    if ties:
        parts.append(natural_join([d["label"] for d in ties]) + " at parity")

    if not parts:
        return "Insufficient data for current-read summary."
    return "; ".join(parts) + "."


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
            "Compute score (TOP500 only) significantly understates China\u2019s actual HPC "
            "capacity. Frontier Models score reflects HF Hub activity only. "
            "See data/executive_summary.json dimension caveats and docs/methodology.html "
            "for full details."
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
