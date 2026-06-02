# Job Hunt Automation Template

This repository automates job discovery across multiple locations, fit scoring, resume tailoring,
cover letter generation, and PDF output for a configurable job search. The pipeline uses direct
ATS APIs, HTTP/BeautifulSoup, Playwright, an ephemeral SearXNG container, and optional paid
search APIs.

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

**Free — no API key required:**

- **Direct company career pages** — the pipeline visits each URL in your
  `config/search_config.yml` company list.
- **Direct ATS APIs** — Greenhouse, Lever, Ashby, and SmartRecruiters career pages are read
  through their public job APIs.
- **SearXNG** — a free search engine GitHub Actions starts temporarily during each run.
  No account needed.
- **ArbeitNow** — a free EU job board, enabled by default.

**Requires an API key:**

- **Brave, Tavily, or Exa** — paid search APIs. Add one for broader discovery beyond
  SearXNG results. Add the key as a GitHub secret and it will be used automatically.
- **RapidAPI / JobSpy** — searches Google Jobs and Indeed. Set `jobspy.enabled: true` in
  `config/search_config.yml` and add `RAPIDAPI_KEY`.

**Uses LLM credits:**

- **AI web search** — when enabled, uses your LLM provider to run site-specific searches
  by job title and region across Greenhouse, Lever, Ashby, and similar ATS boards. Disable
  when you want to conserve credits.

The provider fallback order is set in `config/api_config.yml`:

```yaml
http:
  search_providers:
    order:
      - searxng
      - brave
      - tavily
      - exa
```

If a provider fails, the pipeline continues with the next one.

Every result — regardless of source — passes through URL verification, full job description
fetching, freshness validation, and fit scoring before tailoring or cover letter generation.

`config/discovery_cache.yml` stores URLs already seen in broad discovery so future runs skip
them without repeating search calls.

**LLM providers:**

| Provider | GitHub secret | Notes |
|---|---|---|
| Anthropic (recommended) | `ANTHROPIC_API_KEY` | Reliable at all tiers |
| OpenAI | `OPENAI_API_KEY` | Use `gpt-4o-mini` for lower cost |
| Google | `GOOGLE_API_KEY` | Free tier: set `max_workers: 2` in api_config.yml |
| Ollama | none | Self-hosted local models |

Set `secrets.<provider>.required: true` only for the provider you use.

**Parallelism:** `llm.max_workers` (default `5`) controls concurrent LLM calls.
For Google free tier, start with `max_workers: 2` and configure
`llm.rate_limits.google.requests_per_minute`. `scraping.max_workers` (default `10`)
controls concurrent company scrapes. The LLM client retries 429s and transient errors
automatically.

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
| `config/api_config.yml` | Model/provider, concurrency, rate limits, search-provider order, AI web search, or JD enrichment changes |
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
