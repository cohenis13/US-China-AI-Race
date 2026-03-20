# U.S.–China AI Race Tracker

A live, auto-updating public dashboard tracking the state of the U.S.–China AI competition across six dimensions.

**Live site:** [your-vercel-url.vercel.app](https://your-vercel-url.vercel.app)

---

## What this is

A credible, data-driven tracker that measures the U.S.–China AI race using publicly available data. Built for policy audiences, AI practitioners, and informed general readers. Designed to update automatically without manual intervention.

**Six dimensions tracked:**
1. Frontier Models ← *live data (v1)*
2. Talent ← *live data (v1)*
3. Compute ← *live data (v1)*
4. Adoption ← *live data (v1) — public company filing disclosure rate*
5. Global Diffusion
6. Energy

---

## How it works

```
Hugging Face Hub API
        ↓
scripts/fetch_frontier_models.py   (runs daily via GitHub Actions)
        ↓
data/frontier_models.json          (committed to repo)
        ↓
index.html                         (reads JSON via fetch(), renders chart)
        ↓
Vercel                             (auto-deploys on every commit)
```

The Python script runs daily at 06:00 UTC, fetches model update data from Hugging Face Hub, classifies models by country using the lab mapping in `data/labs.json`, and commits the updated JSON to the repo. Vercel picks up the commit and redeploys within ~30 seconds.

---

## Repo structure

```
/
├── index.html                  Main dashboard
├── data/
│   ├── frontier_models.json    Live data output — Frontier Models (auto-updated)
│   ├── talent.json             Live data output — Talent (auto-updated)
│   ├── labs.json               Manual lab-to-country mapping (Frontier Models)
│   └── institutions.json       Institution keyword lists (Talent classification)
├── scripts/
│   ├── fetch_frontier_models.py  Frontier Models fetch script
│   ├── fetch_talent.py           Talent fetch script
│   ├── fetch_compute.py          Compute fetch script
│   └── fetch_adoption.py         Adoption fetch script
├── .github/
│   └── workflows/
│       ├── update_frontier_models.yml  Daily refresh (06:00 UTC)
│       ├── update_talent.yml           Daily refresh (07:00 UTC)
│       ├── update_compute.yml          Daily refresh (08:00 UTC)
│       └── update_adoption.yml         Daily refresh (09:00 UTC)
├── docs/
│   └── methodology.html        Methodology page
└── README.md
```

---

## Setup

### 1. Create a GitHub repo

Go to [github.com/new](https://github.com/new), create a new **public** repository, then run:

```bash
cd ~/Documents/us-china-ai-tracker
git init
git add .
git commit -m "Initial commit: v1 frontier models tracker"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

### 2. Connect to Vercel

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click "Add New → Project"
3. Import your GitHub repo
4. Set the **Root Directory** to `/` (default)
5. Set the **Framework Preset** to "Other" (this is a static HTML project)
6. Click Deploy

Vercel will now auto-deploy on every push to `main`.

### 3. Trigger the first data refresh

1. Go to your GitHub repo → **Actions** tab
2. Click **"Update Frontier Models Data"**
3. Click **"Run workflow"** → **"Run workflow"**
4. Wait ~2 minutes for it to complete
5. Your `data/frontier_models.json` will be populated with real data
6. Vercel will auto-deploy with the new data

After this first run, data updates automatically every day at 06:00 UTC.

---

## Editing the lab list

The lab-to-country mapping is in `data/labs.json`. To add a lab:

```json
{
  "name": "Your Lab Name",
  "country": "US",
  "hf_authors": ["their-hf-org-slug"],
  "notes": "Brief description."
}
```

Valid country values: `"US"`, `"China"`, `"Other"` (identified lab outside US/China), `"Unknown"` (genuinely unclassifiable)

The `hf_authors` array accepts one or more Hugging Face organization slugs (as they appear in huggingface.co/ORG_SLUG).

---

## Running the fetch scripts locally

If you have Python 3.9+ installed:

```bash
pip install requests

# Frontier Models (Hugging Face Hub)
python scripts/fetch_frontier_models.py
# → writes data/frontier_models.json

# Talent (OpenAlex API)
python scripts/fetch_talent.py
# → writes data/talent.json

# Compute (TOP500 HTML scrape)
python scripts/fetch_compute.py
# → writes data/compute.json

# Adoption (SEC EDGAR EFTS per-company filing search)
python scripts/fetch_adoption.py
# → writes data/adoption.json
```

The Talent script makes two calls to the OpenAlex API and completes in a few seconds.

The Compute script downloads the full TOP500 XML file (~600 KB, all 500 systems) and produces two metrics: aggregate HPL Rmax performance in PFlop/s (primary) and system count (secondary). Rmax is stored in GFlop/s in the source and converted to PFlop/s.

---

## Adding a new dimension

To add a new data dimension (e.g., compute, talent), follow this pattern:

1. **Define the metric:** What exactly are you measuring? What's the v1 proxy?
2. **Find a public data source:** API, public dataset, or scraped data
3. **Create `scripts/fetch_<dimension>.py`:** Follow the structure of `fetch_frontier_models.py`
4. **Create `data/<dimension>.json`:** Same schema (dimension, fetched_at, summary, source, methodology_note)
5. **Add a workflow:** Copy `.github/workflows/update_frontier_models.yml`, replace the script name and schedule
6. **Add a section to `index.html`:** Use the existing live section as a template
7. **Update `docs/methodology.html`**

See `docs/methodology.html` for the data schema.

---

## Methodology

See [docs/methodology.html](docs/methodology.html) for:
- What each metric measures and why
- Data sources and API endpoints
- Classification logic (how labs are assigned to countries)
- Known limitations and caveats

**Key caveat — Frontier Models (v1):** Measures public model update activity on Hugging Face Hub from tracked labs — a proxy for lab output velocity, not a definitive ranking of frontier model capability. Closed models (GPT-4o, Claude, Gemini Ultra) are not counted. Labs are classified into four categories: US, China, Other (identified non-US/non-China labs), and Unknown.

**Key caveat — Talent (v1):** Measures AI research paper volume from OpenAlex (AI, ML, NLP, CV concepts) over the last 12 months — a proxy for research output, not a measure of researcher headcount, citation impact, or capability. Papers are attributed by country of author institution using OpenAlex's pre-computed affiliation data. Multinational papers are counted in each country represented, so country totals can exceed the total paper count. Unknown reflects papers with no identified institutional affiliation in OpenAlex.

**Key caveat — Compute (v1):** Measures aggregate HPL Rmax benchmark performance and system count from the TOP500 supercomputer list — a proxy for disclosed high-end compute capacity, not a direct measure of AI training capability. Excludes private AI clusters and systems not submitted to TOP500. China is known to operate exascale systems not listed on TOP500, so its disclosed capacity is likely a significant undercount.

**Key caveat — Adoption (v1):** Measures the share of major listed companies in each country whose latest annual filing (10-K / 20-F) mentions "generative AI" or "large language model" — a proxy for AI deployment disclosure among large firms, not a measure of all firms or total AI usage. US sample: ~25 major S&P 500 companies. China sample: ~20 major Chinese ADRs filing 20-F with the SEC (does not include Tencent, ByteDance, or non-SEC filers). China sample is tech-sector-heavy, which likely overstates economy-wide adoption. Compare directionally only.

---

## License

Data and code are provided for research, educational, and policy purposes. Source attribution required for republication.
