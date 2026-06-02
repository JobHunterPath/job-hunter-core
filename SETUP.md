# Setup Guide

This guide walks you through forking the template, configuring your profile, and running your first pipeline.

---

## Prerequisites

- A **GitHub account** — free at [github.com](https://github.com)
- An **LLM API key** — Anthropic Claude (recommended), OpenAI, or Google Gemini
- Optional: a **Brave**, **Tavily**, or **Exa** API key for AI-assisted search (improves coverage)

---

## Step 1 — Use the template

1. Go to [github.com/JobHunterPath/job-hunter-template](https://github.com/JobHunterPath/job-hunter-template).
2. Click **"Use this template"** → **"Create a new repository"**.
3. Set the owner to your own GitHub account and give the repo any name you like.
4. Set visibility to **Private** — your resume and personal details will be stored here.
5. Click **Create repository**, then clone it locally:
   ```
   git clone <your-repo-url>
   cd <repo-name>
   ```

---

## Step 2 — Add API keys

Go to your repo on GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Add the secrets that match the providers you plan to use:

| Secret name | Provider | Where to get it | Required? |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Claude | [console.anthropic.com](https://console.anthropic.com) | If using Anthropic (default) |
| `OPENAI_API_KEY` | OpenAI | [platform.openai.com](https://platform.openai.com) | If using OpenAI |
| `GOOGLE_API_KEY` | Google Gemini | [ai.google.dev](https://ai.google.dev) | If using Google |
| `BRAVE_API_KEY` | Brave Search | [api.search.brave.com](https://api.search.brave.com) | Optional; recommended |
| `TAVILY_API_KEY` | Tavily | [tavily.com](https://tavily.com) | Optional; recommended |
| `EXA_API_KEY` | Exa | [exa.ai](https://exa.ai) | Optional |
| `ADZUNA_APP_ID` | Adzuna | [developer.adzuna.com](https://developer.adzuna.com) | Optional; UK/DE/AU coverage |
| `ADZUNA_API_KEY` | Adzuna | same as above | Optional; pair with `ADZUNA_APP_ID` |
| `REED_API_KEY` | Reed.co.uk | [reed.co.uk/developers](https://www.reed.co.uk/developers) | Optional; UK-focused |
| `RAPIDAPI_KEY` | RapidAPI / JSearch | [rapidapi.com](https://rapidapi.com) | Optional |

At minimum you need one LLM key (Anthropic recommended). You do not need all of them.

---

## Step 3 — Configure your search

**Edit `config/api_config.yml`**

Set `llm.default_provider` to your LLM provider (`anthropic`, `openai`, or `google`) and update the model names under `llm.models` for each role (scoring, tailoring, cover_letter, etc.). The defaults use Anthropic Claude.

See `config/templates/api_config.yml` for a fully commented reference.

**Edit `config/search_config.yml`**

Add your target regions, company career page URLs, and job titles. See `config/templates/search_config.yml` for annotated examples.

**Edit `config/scoring_config.yml`**

Set `min_fit_score` to the threshold below which jobs are skipped. See `config/templates/scoring_config.yml` for the full reference.

---

## Step 4 — Add your resume and stories

Replace `context/resume_double_column.tex` (or `resume_single_column.tex`) with your own LaTeX resume. If you are new to LaTeX, the templates include inline comments to guide you.

Edit `context/story_bank.md` and add your STAR-format work stories in the Final section. These are used by the LLM to tailor bullet points and write cover letters.

---

## Step 5 — Run

**Via GitHub Actions (recommended)**

1. Go to your repo on GitHub → **Actions** tab.
2. Click **`job_hunt`** → **Run workflow** (select your region).

The workflow scrapes jobs, scores them, and for qualifying jobs produces a tailored resume, cover letter, and PDF in `outputs/`.

To tailor a specific job URL directly: **Actions** → **`tailor_links`** → paste the job URL.

**Running locally (Docker)**

```bash
docker pull ghcr.io/jobhunterpath/job-hunter-core:latest
docker run --rm \
  -v $(pwd)/config:/workspace/config \
  -v $(pwd)/context:/workspace/context \
  -v $(pwd)/outputs:/workspace/outputs \
  -e ANTHROPIC_API_KEY=your-key \
  ghcr.io/jobhunterpath/job-hunter-core:latest \
  job-hunter hunt --region primary
```

Create a `.env` file in your repo root (it is gitignored) with the same key names from the secrets table and pass it via `--env-file .env` instead of individual `-e` flags.

---

## Keeping up to date

**Actions** → **`Update From Template`** → **Run workflow** → review and merge the generated PR.

---

## Configuration reference

Every config key is documented with inline comments in `config/templates/`. Start there before editing your live `config/` files.

| Template file | What it configures |
|---|---|
| `config/templates/api_config.yml` | LLM provider, model per role, API keys, HTTP settings |
| `config/templates/search_config.yml` | Regions, companies, job titles, exclusion rules |
| `config/templates/scoring_config.yml` | Score thresholds, weighting, APPLY/MAYBE/SKIP cutoffs |
