#!/usr/bin/env python3
"""
Global AI Diffusion Index — composite proxy for external spread of US vs China AI stacks.

APPROACH
  Measures how far U.S. and Chinese AI stacks have spread outside their home markets,
  using two public proxies. Both proxies are scored as a share of the combined
  U.S. + China total, so the two composite scores always sum to 100.

  Proxy 1 — HF Open-Model Monthly Downloads (55% weight, LIVE):
    Sum of monthly downloads across the top-100 most-downloaded models per tracked
    lab, sourced from the Hugging Face Hub API. Unlike fetch_frontier_models.py,
    there is NO date filter — this captures the full installed base of model
    downloads as a measure of active ecosystem reach, not just recent activity.
    Labs and country mappings are loaded from data/labs.json (shared with all
    other live dimensions).

    Why this proxy: Open model downloads are a direct, high-frequency, publicly
    auditable signal of how widely a country's AI models are being actively used
    by developers and organizations worldwide. A model being downloaded millions
    of times per month is embedded in products, pipelines, and research globally.

  Proxy 2 — Cloud AI Platform International Footprint (45% weight, CURATED):
    The number of international countries and territories served by each country's
    major public cloud providers with AI/ML platform services. This measures the
    physical infrastructure layer through which AI capabilities are delivered to
    foreign markets.

    U.S. (AWS + Azure + Google Cloud): ~190 countries/territories
    China (Alibaba Cloud + Huawei Cloud + Tencent Cloud): ~70 countries/territories
    Source: Official provider documentation, Q1 2026.

    Why this proxy: Cloud footprint is the infrastructure layer of AI diffusion.
    A country that cannot access a cloud provider's AI APIs or platforms cannot
    easily adopt that country's AI stack. Footprint data is verifiable and
    directly country-comparable.

COMPOSITE CONSTRUCTION
  Both proxies are expressed as "share of combined US + China" (0-100):
    hf_share_US    = US_downloads  / (US_downloads + China_downloads) * 100
    hf_share_China = China_downloads / (US_downloads + China_downloads) * 100

    cloud_share_US    = US_countries  / (US_countries + China_countries) * 100
    cloud_share_China = China_countries / (US_countries + China_countries) * 100

  Composite:
    US_composite    = WEIGHT_HF * hf_share_US    + WEIGHT_CLOUD * cloud_share_US
    China_composite = WEIGHT_HF * hf_share_China + WEIGHT_CLOUD * cloud_share_China

  By construction, US_composite + China_composite = 100.

  The HF proxy is weighted higher (55%) because it provides a live, high-frequency
  signal of actual global model adoption. Cloud footprint (45%) is structural and
  changes more slowly but captures the infrastructure layer of diffusion.

TO UPDATE CLOUD FOOTPRINT DATA
  When provider footprint figures change (e.g., a new regional expansion), update
  the values in CLOUD_FOOTPRINT below. Expected annual review cadence.

  U.S. providers:
    AWS: ~245 countries and territories served (S3/CloudFront availability as proxy)
    Azure: ~60 regions across ~32 countries; AI/ML services available in ~140 countries
    Google Cloud: 40+ regions; products available in 200+ countries
    Combined footprint (deduplicated estimate): ~190 international countries

  China providers:
    Alibaba Cloud: ~30 countries/regions with local availability zones
    Huawei Cloud: ~30 countries/regions
    Tencent Cloud: ~26 countries/regions
    Combined footprint (deduplicated estimate): ~70 international countries

  Note: The combined figure uses a deduplicated estimate. Individual provider
  figures overlap heavily on major markets.

Outputs to data/diffusion.json.
"""

import json
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required.")
    print("Install it with:  pip install requests")
    sys.exit(1)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
LABS_FILE   = ROOT / "data" / "labs.json"
OUTPUT_FILE = ROOT / "data" / "diffusion.json"

# ── Config ────────────────────────────────────────────────────────────────────
HF_API_BASE         = "https://huggingface.co/api/models"
REQUEST_TIMEOUT     = 20          # seconds
RATE_LIMIT_SLEEP    = 0.4         # seconds between API calls
RESULTS_PER_AUTHOR  = 100         # top-N most-downloaded models per author

# ── Composite weights ─────────────────────────────────────────────────────────
WEIGHT_HF    = 0.55   # HF open-model monthly downloads (live)
WEIGHT_CLOUD = 0.45   # cloud AI platform international footprint (curated)

# ── Proxy 2: Cloud AI Platform International Footprint ───────────────────────
# Source: Official cloud provider documentation and coverage pages, Q1 2026.
# Definition: Number of international countries/territories served with AI/ML
# platform services by each country's major public cloud providers (combined,
# deduplicated estimate).
#
# U.S. providers (AWS, Azure, Google Cloud): ~190 countries/territories
#   - AWS: ~245 countries/territories (S3/service availability)
#   - Azure AI: available in ~140 countries across ~60 regions
#   - Google Cloud AI: available in 200+ countries/territories
#   Combined deduplicated estimate: ~190 (saturates most of the accessible world)
#
# China providers (Alibaba Cloud, Huawei Cloud, Tencent Cloud): ~70 countries/territories
#   - Alibaba Cloud: ~30 countries/regions with local availability zones
#   - Huawei Cloud: ~30 countries/regions
#   - Tencent Cloud: ~26 countries/regions
#   Combined deduplicated estimate: ~70
#
# Note: The U.S. figure reflects near-global coverage of accessible markets.
# The China figure reflects deliberate geographic expansion under BRI and
# enterprise cloud strategy, but remains concentrated in Asia-Pacific, Middle
# East, Africa, and selected European/Latin American markets.
#
# TO UPDATE: Change value and note when provider coverage pages show significant
# expansion. Annual review recommended.
CLOUD_FOOTPRINT = {
    "US": {
        "value":    190,
        "coverage": "high",
        "note": (
            "Combined international footprint of AWS, Microsoft Azure, and "
            "Google Cloud AI/ML platform services — Q1 2026 official "
            "provider documentation. Deduplicated country/territory estimate."
        ),
        "providers": "AWS + Microsoft Azure + Google Cloud",
    },
    "China": {
        "value":    70,
        "coverage": "high",
        "note": (
            "Combined international footprint of Alibaba Cloud, Huawei Cloud, "
            "and Tencent Cloud AI/ML platform services — Q1 2026 official "
            "provider documentation. Deduplicated country/territory estimate."
        ),
        "providers": "Alibaba Cloud + Huawei Cloud + Tencent Cloud",
    },
}

CLOUD_FOOTPRINT_META = {
    "source_name":    "Cloud provider official documentation (AWS, Azure, Google Cloud, Alibaba Cloud, Huawei Cloud, Tencent Cloud)",
    "source_url":     "https://aws.amazon.com/about-aws/global-infrastructure/",
    "edition":        "Q1 2026",
    "definition":     "International countries/territories served by major cloud AI/ML platform services (combined, deduplicated estimate)",
    "update_cadence": "Annual review — update when providers announce significant geographic expansion",
}


# ── Labs ──────────────────────────────────────────────────────────────────────
def load_labs() -> list[dict]:
    if not LABS_FILE.exists():
        log.error("labs.json not found at %s", LABS_FILE)
        sys.exit(1)
    with open(LABS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["labs"]


# ── HF API ────────────────────────────────────────────────────────────────────
def fetch_downloads_for_author(author: str) -> int:
    """
    Fetch total monthly downloads across the top-N most-downloaded models
    for a given HF author. Returns 0 on failure (non-fatal).
    """
    url = (
        f"{HF_API_BASE}"
        f"?author={author}"
        f"&sort=downloads"
        f"&direction=-1"
        f"&limit={RESULTS_PER_AUTHOR}"
    )
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        models = resp.json()
    except requests.exceptions.HTTPError as e:
        log.warning("HTTP error for author '%s': %s", author, e)
        return 0
    except requests.exceptions.RequestException as e:
        log.warning("Request failed for author '%s': %s", author, e)
        return 0

    total = sum(m.get("downloads", 0) or 0 for m in models)
    log.info("    → %d model(s), %s downloads", len(models), f"{total:,}")
    return total


# ── Share-of-combined scoring ─────────────────────────────────────────────────
def share_score(country_value: float, total: float) -> float | None:
    """Return country_value / total * 100, rounded to 1 dp. None if total == 0."""
    if total <= 0:
        return None
    return round(country_value / total * 100.0, 1)


# ── Composite ─────────────────────────────────────────────────────────────────
def compute_composite(hf_share: float | None, cloud_share: float | None) -> dict:
    """
    Weighted composite of two share-of-combined scores.
    If one proxy is unavailable, re-weight the remaining proxy to 100%.
    """
    available = []
    if hf_share    is not None: available.append(("hf_downloads",   hf_share,    WEIGHT_HF))
    if cloud_share is not None: available.append(("cloud_footprint", cloud_share, WEIGHT_CLOUD))

    if not available:
        return {"composite_score": None, "effective_weights": {}}

    total_weight = sum(w for _, _, w in available)
    composite    = sum(v * (w / total_weight) for _, v, w in available)
    eff_weights  = {k: round(w / total_weight, 4) for k, _, w in available}

    return {
        "composite_score":   round(composite, 1),
        "effective_weights": eff_weights,
    }


def interpretive_sentence(us_score: float | None, cn_score: float | None,
                           us_hf: float | None, cn_hf: float | None,
                           us_cloud: float | None, cn_cloud: float | None) -> str:
    if us_score is None or cn_score is None:
        return "Insufficient data to compare global diffusion at this time."
    leader = "U.S." if us_score >= cn_score else "China"
    leader_score = max(us_score, cn_score)
    other_score  = min(us_score, cn_score)
    gap = round(leader_score - other_score, 1)

    hf_note = ""
    if us_hf is not None and cn_hf is not None:
        hf_leader = "U.S." if us_hf >= cn_hf else "China"
        hf_note = (
            f" On open-model downloads, {hf_leader} accounts for "
            f"{max(us_hf, cn_hf):.1f}% of the combined U.S.\u2013China total."
        )

    return (
        f"{leader}-origin AI stacks account for approximately {leader_score:.1f}% "
        f"of the measured U.S.\u2013China global diffusion footprint "
        f"({gap:.1f}-point lead over {('China' if leader == 'U.S.' else 'U.S.')})."
        f"{hf_note}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    labs = load_labs()
    now  = datetime.now(timezone.utc)

    log.info("Labs loaded: %d entries", len(labs))
    log.info("Fetching HF monthly downloads for US and China labs...")

    # ── Proxy 1: HF downloads per country ────────────────────────────────────
    hf_downloads: dict[str, int] = {"US": 0, "China": 0}
    hf_lab_detail: dict[str, list[dict]] = {"US": [], "China": []}

    for lab in labs:
        country    = lab.get("country", "Unknown")
        if country not in ("US", "China"):
            continue
        lab_name   = lab["name"]
        hf_authors = lab.get("hf_authors", [])

        for author in hf_authors:
            log.info("  Fetching %-30s [%s / %s]", author, lab_name, country)
            dl = fetch_downloads_for_author(author)
            hf_downloads[country] += dl
            hf_lab_detail[country].append({
                "lab":      lab_name,
                "author":   author,
                "downloads": dl,
            })
            time.sleep(RATE_LIMIT_SLEEP)

    us_dl    = hf_downloads["US"]
    china_dl = hf_downloads["China"]
    hf_total = us_dl + china_dl

    log.info("HF downloads — US: %s  China: %s  Total: %s",
             f"{us_dl:,}", f"{china_dl:,}", f"{hf_total:,}")

    us_hf_share    = share_score(us_dl,    hf_total)
    china_hf_share = share_score(china_dl, hf_total)

    # ── Proxy 2: Cloud footprint (curated) ───────────────────────────────────
    us_cloud_val    = CLOUD_FOOTPRINT["US"]["value"]
    china_cloud_val = CLOUD_FOOTPRINT["China"]["value"]
    cloud_total     = us_cloud_val + china_cloud_val

    us_cloud_share    = share_score(us_cloud_val,    cloud_total)
    china_cloud_share = share_score(china_cloud_val, cloud_total)

    log.info("Cloud footprint — US: %d  China: %d", us_cloud_val, china_cloud_val)

    # ── Composite ─────────────────────────────────────────────────────────────
    us_comp    = compute_composite(us_hf_share,    us_cloud_share)
    china_comp = compute_composite(china_hf_share, china_cloud_share)

    us_score    = us_comp["composite_score"]
    china_score = china_comp["composite_score"]

    # ── Output ────────────────────────────────────────────────────────────────
    output = {
        "dimension":   "diffusion",
        "metric_key":  "ai_diffusion_composite_index",
        "title":       "Global AI Diffusion — U.S. vs China",
        "subtitle": (
            "Share of combined U.S.\u2013China global AI diffusion footprint, "
            "measured by open-model ecosystem reach and cloud infrastructure coverage. "
            "U.S. + China scores sum to 100."
        ),
        "description": (
            "A two-proxy composite index measuring how far U.S. and Chinese AI stacks "
            "have spread beyond their home markets. Combines HF open-model monthly "
            "downloads (live, from data/labs.json tracked labs) with cloud AI platform "
            "international footprint (curated, annually reviewed). Both proxies are "
            "scored as share-of-combined so U.S. + China = 100."
        ),
        "fetched_at":   now.isoformat(),
        "last_updated": now.isoformat(),
        "summary": {
            "US": {
                "composite_score":   us_score,
                "effective_weights": us_comp["effective_weights"],
                "proxies": {
                    "hf_downloads": {
                        "raw_value":   us_dl,
                        "unit":        "monthly downloads (HF Hub)",
                        "share_score": us_hf_share,
                        "coverage":    "high",
                        "note": (
                            f"Sum of monthly downloads across top-{RESULTS_PER_AUTHOR} "
                            "models per US-attributed lab on Hugging Face Hub. "
                            "Labs sourced from data/labs.json."
                        ),
                        "lab_detail": hf_lab_detail["US"],
                    },
                    "cloud_footprint": {
                        "raw_value":   us_cloud_val,
                        "unit":        "international countries/territories",
                        "share_score": us_cloud_share,
                        "coverage":    CLOUD_FOOTPRINT["US"]["coverage"],
                        "note":        CLOUD_FOOTPRINT["US"]["note"],
                        "providers":   CLOUD_FOOTPRINT["US"]["providers"],
                    },
                },
            },
            "China": {
                "composite_score":   china_score,
                "effective_weights": china_comp["effective_weights"],
                "proxies": {
                    "hf_downloads": {
                        "raw_value":   china_dl,
                        "unit":        "monthly downloads (HF Hub)",
                        "share_score": china_hf_share,
                        "coverage":    "high",
                        "note": (
                            f"Sum of monthly downloads across top-{RESULTS_PER_AUTHOR} "
                            "models per China-attributed lab on Hugging Face Hub. "
                            "Labs sourced from data/labs.json."
                        ),
                        "lab_detail": hf_lab_detail["China"],
                    },
                    "cloud_footprint": {
                        "raw_value":   china_cloud_val,
                        "unit":        "international countries/territories",
                        "share_score": china_cloud_share,
                        "coverage":    CLOUD_FOOTPRINT["China"]["coverage"],
                        "note":        CLOUD_FOOTPRINT["China"]["note"],
                        "providers":   CLOUD_FOOTPRINT["China"]["providers"],
                    },
                },
            },
        },
        "interpretive_sentence": interpretive_sentence(
            us_score, china_score,
            us_hf_share, china_hf_share,
            us_cloud_share, china_cloud_share,
        ),
        "composite_construction": {
            "method": (
                "Both proxies are scored as share-of-combined (US + China = 100). "
                f"HF downloads: (country_downloads / total_downloads) \u00d7 100. "
                f"Cloud footprint: (country_countries / total_countries) \u00d7 100. "
                f"Composite = {WEIGHT_HF} \u00d7 hf_share + {WEIGHT_CLOUD} \u00d7 cloud_share. "
                "By construction, US composite + China composite = 100."
            ),
            "weights": {
                "hf_downloads":   WEIGHT_HF,
                "cloud_footprint": WEIGHT_CLOUD,
            },
            "scoring": "share-of-combined (US + China = 100)",
        },
        "proxies_meta": {
            "hf_downloads": {
                "source_name":    "Hugging Face Hub API",
                "source_url":     HF_API_BASE,
                "definition":     f"Sum of monthly downloads across top-{RESULTS_PER_AUTHOR} most-downloaded models per tracked lab. No date filter — captures full active install base.",
                "update_cadence": "Daily (live API — downloads reflect trailing 30 days)",
                "labs_source":    "data/labs.json (shared with all live dimensions)",
            },
            "cloud_footprint": CLOUD_FOOTPRINT_META,
        },
        "methodology_note": (
            "This index measures external diffusion — how far U.S. and Chinese AI "
            "stacks have spread beyond their home markets — not domestic adoption. "
            "HF downloads are the strongest live signal: a model being downloaded "
            "globally indicates active embedding in foreign products and pipelines. "
            "Cloud footprint measures the infrastructure layer through which AI "
            "services are delivered internationally. "
            "Known limitations: HF Hub undercounts Chinese models that are primarily "
            "distributed through domestic platforms (ModelScope, Gitee AI). The cloud "
            "footprint is a count of countries served, not revenue or usage depth. "
            "Both proxies measure reach, not quality or economic impact of diffusion."
        ),
        "coverage_note": (
            "HF downloads: high confidence — directly measured from public API. "
            "May undercount Chinese model reach (ModelScope, domestic platforms). "
            "Cloud footprint: high confidence for both countries — based on official "
            "provider documentation. U.S. figure near-saturates accessible global "
            "markets; Chinese figure reflects documented international expansion."
        ),
        "what_this_does_not_capture": [
            "Domestic AI adoption within each country's home market",
            "Chinese model downloads via ModelScope, Gitee AI, or other domestic platforms",
            "Closed/proprietary model API usage (GPT-4o, Claude, Gemini, Qianwen API)",
            "AI hardware exports (chips, servers) as a diffusion vector",
            "Influence via joint ventures, technical assistance, or standards bodies",
            "Quality or depth of AI integration in foreign deployments",
            "Revenue or economic impact of diffusion",
        ],
        "sources": [
            {
                "proxy":   "hf_downloads",
                "name":    "Hugging Face Hub API",
                "url":     HF_API_BASE,
                "edition": "Live (daily refresh)",
            },
            {
                "proxy":   "cloud_footprint",
                "name":    "AWS Global Infrastructure",
                "url":     "https://aws.amazon.com/about-aws/global-infrastructure/",
                "edition": "Q1 2026",
            },
            {
                "proxy":   "cloud_footprint",
                "name":    "Microsoft Azure global infrastructure",
                "url":     "https://azure.microsoft.com/en-us/explore/global-infrastructure/geographies/",
                "edition": "Q1 2026",
            },
            {
                "proxy":   "cloud_footprint",
                "name":    "Google Cloud locations",
                "url":     "https://cloud.google.com/about/locations",
                "edition": "Q1 2026",
            },
            {
                "proxy":   "cloud_footprint",
                "name":    "Alibaba Cloud global infrastructure",
                "url":     "https://www.alibabacloud.com/global-locations",
                "edition": "Q1 2026",
            },
            {
                "proxy":   "cloud_footprint",
                "name":    "Huawei Cloud regions",
                "url":     "https://www.huaweicloud.com/intl/en-us/global/",
                "edition": "Q1 2026",
            },
            {
                "proxy":   "cloud_footprint",
                "name":    "Tencent Cloud regions",
                "url":     "https://www.tencentcloud.com/document/product/213/6091",
                "edition": "Q1 2026",
            },
        ],
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    log.info("")
    log.info("Output written to: %s", OUTPUT_FILE)
    log.info("US composite:    %s", us_score)
    log.info("China composite: %s", china_score)
    if us_score is not None and china_score is not None:
        gap    = abs(us_score - china_score)
        leader = "US" if us_score > china_score else "China"
        log.info("Leader: %s (gap: %.1f points)", leader, gap)


if __name__ == "__main__":
    main()
