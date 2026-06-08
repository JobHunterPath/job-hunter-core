# Job Hunt Automation Template

This repository automates job discovery across multiple locations, fit scoring, resume tailoring,
cover letter generation, and PDF output for a configurable job search. The pipeline uses direct
ATS APIs, HTTP/BeautifulSoup, Playwright, an ephemeral SearXNG container, and optional
search APIs with free tiers.

It also includes an optional LinkedIn content and networking system. The LinkedIn workflow
is disabled by default; when enabled, it generates public-safe post ideas from your private
story bank, creates weekly draft posts for review, and suggests recruiters, peers, creators,
and posts for manual engagement. It never posts, comments, follows, connects, messages, or
likes automatically.

## Start Here

Read [SETUP.md](SETUP.md) first. It walks through initial setup step by step, including how
to build your story bank, choose a resume layout, configure
job search, and run the automation from GitHub. It also includes AI prompts you can use to
prepare each personal file.

When using AI helpers in VS Code, use them only for personal setup files such as the story
bank, resume, and configs. Do not ask them to change workflows or
automation-owned files in your local repo — those are maintained centrally and your changes
would be overwritten on the next update.

The GitHub workflows run a maintained public core image with Python, Playwright, LaTeX, and
the job-hunt CLI already installed. Your repository keeps only configuration, resume/source
material, workflows, and generated outputs.

For future updates, run **Actions → Update From Template** in your own repo. It opens a pull
request that imports the latest maintained workflows, docs, and missing config defaults while
preserving your existing config values, resume, story bank, and generated jobs.

## What Runs By Default

Once setup is complete, the pipeline runs on a schedule automatically:

- **Job Hunt** runs once per weekday for your primary region. If you enable additional regions,
  add a matching cron entry for each in `.github/workflows/job_hunt.yml`.
- **Company Discovery** runs manually only. Trigger it from the Actions tab when you want to
  find new career pages to add to your list.
- **LinkedIn jobs** are filtered from search results by default. Individual LinkedIn job pages
  block automated fetching (HTTP 429), so only the search snippet is kept if a listing appears.
- **AI web search** is disabled by default. Enable it in `config/api_config.yml` once you are
  comfortable with API credit usage.

## Job Sources

The pipeline finds jobs through several layers, tried in order from cheapest to most expensive.
**No paid search API key is required for the default run.** Keyed providers are optional
extensions that add breadth when free sources return thin results.

**Free — no API key required:**

- **Direct company career pages** — the pipeline visits each URL in your
  `config/search_config.yml` company list. For each URL it attempts:
  1. Known ATS public endpoints (Greenhouse, Lever, Ashby, SmartRecruiters, Workable,
     Personio, Recruitee, Hibob, Teamtailor, Breezy, Workday) via their job APIs.
  2. `JobPosting` structured data embedded in the page HTML.
  3. Common career-path and sitemap patterns (e.g. `/sitemap.xml`, `/careers`, `/jobs`).
  4. Static HTML extraction and, as a last resort, Playwright rendering for JavaScript-heavy pages.
  The method that succeeded is recorded per-job in the run log.
- **ATS discovery** — the pipeline queries all 11 ATS platforms listed in
  `config/api_config.yml` under `http.search_providers.ats_discovery.sources` directly by
  job title and region. These are public no-key endpoints. Results are deduplicated against
  `config/discovery_cache.yml`.
- **SearXNG** — a free search engine GitHub Actions starts temporarily during each run.
  No account needed.
- **ArbeitNow** — a free EU job board, enabled by default.
- **Broad job boards** — JobSpy, Remotive, and several other boards are queried globally
  and filtered by title and region. JobSpy uses the bundled python-jobspy library and does
  not use `RAPIDAPI_KEY`. Keyed board APIs such as Adzuna, Reed, Jooble, and JSearch are
  listed separately below.

**Requires an API key:**

- **Brave, Tavily, or Exa** — optional search APIs, each with a free tier. Add one for broader discovery
  beyond SearXNG results. Add the key as a GitHub secret and it will be used automatically.
  When a provider's monthly budget is reached (`http.api_budgets.monthly_limits`), it is
  skipped silently and the next provider in the fallback order takes over.
- **RapidAPI / JSearch** — optional aggregate job search through JSearch on RapidAPI.
  Set `http.job_boards.jsearch.enabled: true` in `config/api_config.yml` and add
  `RAPIDAPI_KEY`.

**Uses LLM credits:**

- **AI web search** — when enabled, uses your LLM provider to run site-specific searches
  by job title and region across Greenhouse, Lever, Ashby, and similar ATS boards. Disable
  when you want to conserve credits. Controlled by
  `http.search_providers.ai_web_search.enabled` in `config/api_config.yml`.

If a provider fails or its monthly budget is exhausted, the pipeline continues with the
next one. Exhausted providers are suppressed for the rest of the month without affecting
the failure counter. Paid search APIs (Brave, Tavily, Exa) are used only for global ATS
discovery at the start of each run — never for per-company career page fallback.

Every result — regardless of source — passes through URL verification, full job description
fetching, freshness validation, and fit scoring before tailoring or cover letter generation.

`config/discovery_cache.yml` stores URLs already seen in broad discovery so future runs skip
them without repeating search calls.

## Running Company Discovery Without LLM Sectors

Company Discovery (triggered manually from Actions) uses two paths by default: ATS-posting
discovery and LLM sector suggestions. You can run it in a fully deterministic, no-LLM-sector
mode by setting `discovery.sectors` to an empty list in `config/search_config.yml`:

```yaml
discovery:
  sectors: []
```

With `sectors` empty, the pipeline skips LLM company-name suggestions entirely and discovers
companies only from real job postings found on ATS platforms. This costs no LLM tokens for
the discovery step and produces companies with verified live postings.

## Source-Yield Diagnostics

After every hunt run, the log includes a per-source yield summary. A line such as:

```
[scrape] sources: direct_ats=12 career_page=3 searxng=5 ats_discovery=8 jobspy=2
```

shows how many jobs each source contributed. Use this to identify which sources are
thin before deciding what to change.

What to look for:

- `direct_ats=0` and `career_page=0` — the companies in your `config/search_config.yml`
  list may have no current openings for your titles, or the URLs may be wrong.
- `searxng=0` — SearXNG may not have started cleanly (check the Actions log for container
  startup errors) or may have returned zero results for the configured titles and region.
- `ats_discovery=0` — no live postings found on the 11 ATS platforms for your titles and
  region. This can happen in smaller markets or for niche titles.
- `jobspy=0` — python-jobspy is unavailable, JobSpy is disabled, or the searched boards had
  few matches.
- All sources low — see the troubleshooting section below.

**LLM providers:**

| Provider | GitHub secret | Notes |
|---|---|---|
| Anthropic (recommended) | `ANTHROPIC_API_KEY` | Reliable at all tiers |
| OpenAI | `OPENAI_API_KEY` | Use `gpt-4o-mini` for lower cost |
| Google | `GOOGLE_API_KEY` | Free tier available |
| Ollama | none | Self-hosted local models |

Add the key as a GitHub secret; the pipeline picks it up automatically. The LLM client
retries 429s and transient errors automatically.

## Local Run

The core image is public, so no registry login is needed for local runs.

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/jobhunterpath/job-hunter-core:latest \
  job-hunter hunt
```

For direct job URLs:

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/jobhunterpath/job-hunter-core:latest \
  job-hunter tailor-links --links "https://example.com/job"
```

## Outputs

Generated application files are written to:

```text
jobs/YYYY-MM-DD_company_role/
```

The template includes an empty `jobs/` folder so GitHub Actions can write and commit outputs
on the first run. The tracker in `config/applied_jobs.yml` prevents duplicate processing.

LinkedIn review files are written to:

```text
linkedin/ideas.md
linkedin/drafts/
linkedin/engagement.md
linkedin/networking.md
```

Review everything manually before using it on LinkedIn.

Each hunt run tailors at most 15 matched jobs. If more jobs pass scoring, the pipeline
processes the 15 highest-scoring matches first.

Job-title search policy is driven by `config/search_config.yml`:

- `global_search.job_titles` controls the roles searched across ATS pages, career pages,
  discovery, and search-provider fallbacks.
- `exclusion_rules.excluded_title_terms` blocks irrelevant title terms before expensive
  validation, scoring, tailoring, and PDF work.

Keep those two lists aligned: add the role families you want, and add adjacent roles you
do not want to `excluded_title_terms`.

## Ongoing Configuration

First-time setup lives in [SETUP.md](SETUP.md). After setup, these are the files
people usually keep tuning:

| File | Keep updated when |
|---|---|
| `config/search_config.yml` | Target regions, companies, job titles, exclusions, or scraping breadth change |
| `config/scoring_config.yml` | Fit threshold, seniority filter, or strategic company overrides change |
| `config/tailoring_config.yml` | Resume summary, bullet, project, keyword, or page-limit rules need tuning |
| `config/cover_letter_config.yml` | Candidate background, tone, salutation, or forbidden phrases change |
| `config/api_config.yml` | Model/provider, concurrency, rate limits, source enablement, AI web search, or JD enrichment changes |
| `config/applied_jobs.yml` | You want to reprocess a URL or allow a similar title at the same company |

The pipeline writes `config/applied_jobs.yml` automatically. Edit it manually
only to remove entries you want processed again.

## Applied Jobs

<!-- JOBS_STATS_START -->
No jobs tracked yet.
<!-- JOBS_STATS_END -->

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
<!-- JOBS_TABLE_END -->
