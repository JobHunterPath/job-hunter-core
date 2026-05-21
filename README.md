# Job Hunt Automation Template

This repository automates job discovery across multiple locations, fit scoring, resume tailoring, cover
letter generation, and PDF output for a configurable job search. The scraper
uses optional AI web search by job title and region, direct ATS APIs,
HTTP/BeautifulSoup, Playwright, an ephemeral SearXNG container in GitHub
Actions, and optional search APIs such as Brave, Tavily, and Exa.

It also includes a lightweight LinkedIn content and networking system. The
LinkedIn workflow generates public-safe post ideas from your private story bank,
creates weekly draft posts for review, and suggests people/posts for manual
engagement. It never posts, comments, follows, connects, messages, or likes
automatically.

## Start Here

For initial setup, read [SETUP.md](SETUP.md) first. It walks through the
process step by step, including how to fill in project instructions, build your
story bank, choose a resume layout, configure job search, and run the automation
from GitHub.

When using AI helpers in VS Code, use them only for personal setup files such as
the story bank, resume, project instructions, and configs. Do not ask them to
change workflows or automation-owned files in your local repo. Code fixes should
come through the maintained private core/template workflow.

For future updates, run **Actions -> Update From Core** in your own repo.
It creates a merge commit that imports the latest maintained files to your
selected branch while keeping your resume, story bank, generated jobs, and
config files untouched by default. The workflow summary shows whether the
update is a patch, minor, or major version change. After it finishes,
run `git pull origin main` locally. Detailed step-by-step update instructions
are in [SETUP.md](SETUP.md).

The GitHub workflows run a maintained private core image with Python,
Playwright, LaTeX, and the job-hunt CLI already installed. Your repository keeps
only configuration, resume/source material, workflows, and generated outputs.
If the image is private, the maintainer must grant your repository package
access or you must add a `CORE_IMAGE_PAT` secret with package read access.

## Quick Start

1. Customize `project_instructions.md` with your own profile, ID scheme, and chatbot prompts.
2. Replace `story_bank.md` with raw notes and verified STAR stories from your experience.
3. Choose and customize a LaTeX resume:
   - `resume_double_column.tex` for the AltaCV double-column layout.
   - `resume_single_column.tex` for an ATS-friendly single-column layout.
4. Update every file in `config/`, especially:
   - `api_config.yml`
   - `search_config.yml`
   - `scoring_config.yml`
   - `cover_letter_config.yml`
   - `tailoring_config.yml` (controls what the AI can change, including project
     content selection when an uncommented Projects section exists in your resume)
5. In `config/api_config.yml`, set `profile.resume_tex`, `profile.story_bank`, and `profile.project_instructions`.
6. If you change LLM provider, replace the `llm.models` values, add the matching secret, and set the matching `secrets.<provider>.required` flag.
7. Create and store API keys using the step-by-step instructions in `SETUP.md`.
8. Run the preflight checklist, commit, and push before starting GitHub Actions.
9. Configure `linkedin/config.yml` if you want LinkedIn ideas, drafts, and networking suggestions.

Scheduled GitHub hunts run the primary enabled region every weekday. Secondary
enabled regions run Monday, Wednesday, and Friday. Cron slots are mapped to
enabled regions with companies in `config/search_config.yml`; empty slots exit
before the expensive pipeline steps. Manual **Job Hunt Pipeline** runs include a
`region` field where you can enter `all` or a specific region key from
`config/search_config.yml`.

**Project section tailoring:** When your resume contains an uncommented
Projects section, the tailorer selects and adjusts project content from your
story bank to match each job description. It will never uncomment a
commented-out section or add a new one. Configure the allowed story ID prefixes,
project count, bullet count, and page limit in
`config/tailoring_config.yml` under `tailoring.rules.projects`.

**Scoring prompt size:** `config/scoring_config.yml` includes
`scoring.prompt_context` settings that compact LaTeX boilerplate/comments and
cap resume/JD characters sent to the scoring model without changing scoring
thresholds or strategic overrides.

## Search Fallbacks

Search APIs are optional except for the LLM provider you choose. After direct
ATS, HTTP/BeautifulSoup, and Playwright scraping, the default search-provider
fallback order is configured in `config/api_config.yml`:

For LLM providers, `config/api_config.yml` and GitHub Secrets must agree:

| Provider | Secret |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `google` | `GOOGLE_API_KEY` |
| `ollama` | none for local Ollama |

Set `secrets.<provider>.required: true` only for providers you actually use.

```yaml
http:
  search_providers:
    order:
      - searxng
      - brave
      - tavily
      - exa
```

GitHub Actions starts SearXNG temporarily for each hunt, discovery, and
tailor-links job. If SearXNG or any API provider fails, the pipeline continues
with the next available option.

Broad ATS discovery runs after configured company ATS/API scraping. It searches
title + region for individual ATS posting URLs, follows the provider order above
so SearXNG is tried before Brave/Tavily/Exa, and covers Greenhouse, Lever,
Ashby, SmartRecruiters, Workable, Personio, Recruitee, and HiBob URL shapes.

`config/discovery_cache.yml` stores candidate URLs already seen from broad
discovery sources so future runs do not spend SearXNG/search API/AI calls
rediscovering the same listings.

**JD enrichment:** `http.jd_enrichment` controls best-effort fetching of full job
descriptions for sparse search snippets. LinkedIn job pages often return HTTP
429 to direct fetches, so `linkedin\.com/jobs/` is skipped by default and the
pipeline keeps the search snippet.

AI web search can be enabled in `config/api_config.yml` to search job titles by
region through an LLM provider's web-search tool. It never searches by company
name, and it stops at strict per-run caps before the rest of the pipeline
continues.

```yaml
llm:
  providers:
    ai_web_search: anthropic
  models:
    ai_web_search: "claude-haiku-4-5-20251001"
  max_tokens:
    ai_web_search: 1200

http:
  search_providers:
    ai_web_search:
      enabled: false
      max_prompts_per_run: 80
      max_prompts_per_region: 8
      max_results_per_prompt: 8
      max_results_per_region: 30
      max_total_results_per_run: 120
      min_confidence: 0.5
```

Recommended models: `claude-haiku-4-5-20251001` for Anthropic (switch to
`claude-sonnet-4-6` if you see frequent 529 errors at peak hours),
`gemini-2.5-flash-lite` for Google validation/JD extraction,
`gemini-2.5-flash` or Claude for scoring until you compare score quality, and
`gpt-4o-mini` for OpenAI.
The default sources (`greenhouse`, `lever`, `ashby`, `smartrecruiters`,
`workable`, `personio`, `recruitee`, `hibob`, `generic_web`) target well-indexed
ATS boards and exclude aggregators. Every result still passes through dedupe,
URL verification, JD fetching, validation, and scoring gates before any
tailoring or cover-letter generation happens.

AI web search includes compact exclusion rules from `config/search_config.yml`
in each prompt and filters low-confidence results, source-specific listing/search
pages, stale snippets, and application-shell titles such as `Applying to ...`
before they can spend validation or scoring tokens.

**Parallelism:** company scraping, validation, and scoring all run concurrently.
`llm.max_workers` (default `5`) controls concurrent LLM calls. For Google free
tier, start with `max_workers: 2` and set
`llm.rate_limits.google.requests_per_minute` below the RPM shown in AI Studio.
`scraping.max_workers` (default `10`) in `search_config.yml` controls concurrent
company scrapes. The LLM client retries rate-limit errors (429) and transient
5xx failures automatically with backoff.

## Local Run

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/job-network-projects/job-hunter-core:latest \
  job-hunter hunt
```

For direct job URLs:

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/job-network-projects/job-hunter-core:latest \
  job-hunter tailor-links --links "https://example.com/job"
```

## Outputs

Generated application files are written to:

```text
jobs/YYYY-MM-DD_company_role/
```

The template includes an empty `jobs/` folder so GitHub Actions can write and
commit generated outputs on the first run.

The tracker in `config/applied_jobs.yml` prevents duplicate processing.

LinkedIn review files are written to:

```text
linkedin/ideas.md
linkedin/drafts/
linkedin/engagement.md
linkedin/networking.md
```

Review everything manually before using it on LinkedIn.

Each hunt run tailors at most 15 matched jobs. If more jobs pass scoring, the
pipeline processes the 15 highest-scoring matches first.

Job-title search policy is driven by `config/search_config.yml`:

- `global_search.job_titles` controls the roles searched across ATS pages,
  career pages, discovery, JSearch, and search-provider fallbacks.
- `exclusion_rules.excluded_title_terms` blocks irrelevant title terms before
  expensive validation, scoring, tailoring, and PDF work.

Keep those two lists aligned: add the role families you want to
`global_search.job_titles`, and add adjacent roles you do not want to
`excluded_title_terms`.

## Applied Jobs

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
<!-- JOBS_TABLE_END -->
