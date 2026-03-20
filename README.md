# U.S.–China AI Race Tracker

A live, auto-updating public dashboard tracking the state of the U.S.–China AI competition across six dimensions.

**Live site:** [your-vercel-url.vercel.app](https://your-vercel-url.vercel.app)

---

## What this is

A credible, data-driven tracker that measures the U.S.–China AI race using publicly available data. Built for policy audiences, AI practitioners, and informed general readers. Designed to update automatically without manual intervention.

**Six dimensions tracked:**
1. Frontier Models ← *live data (v1)*
2. Compute
3. Talent
4. Domestic Adoption
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
│   ├── frontier_models.json    Live data output (auto-updated)
│   └── labs.json               Manual lab-to-country mapping (edit this)
├── scripts/
│   └── fetch_frontier_models.py  Data fetch script
├── .github/
│   └── workflows/
│       └── update_frontier_models.yml  Daily refresh
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

Valid country values: `"US"`, `"China"`, `"Unknown"`

The `hf_authors` array accepts one or more Hugging Face organization slugs (as they appear in huggingface.co/ORG_SLUG).

---

## Running the fetch script locally

If you have Python 3.9+ installed:

```bash
pip install requests
python scripts/fetch_frontier_models.py
```

Output will be written to `data/frontier_models.json`.

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

**Key caveat for v1:** The frontier models metric counts model updates on Hugging Face Hub — a useful proxy for lab activity, but not a complete census of all frontier AI development (closed models like GPT-4o are not included).

---

## License

Data and code are provided for research, educational, and policy purposes. Source attribution required for republication.
