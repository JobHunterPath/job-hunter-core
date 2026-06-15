# job-hunter-core

Keep this file in sync with `CLAUDE.md`.

You are working on the automation engine that powers the job search pipeline.

## Architecture

- `src/job_hunter_core/core/` — config loader, llm_client, utils, metrics, config_schema
- `src/job_hunter_core/pipeline/` — orchestrator, scorer, tailorer, cover_writer, enrichment, validator, pdf_compiler, readme_writer, hunt_pipeline, tailor_pipeline
- `src/job_hunter_core/sources/` — ats, adzuna_source, reed_source, jobspy_source, job_boards, search_providers, jd_fetcher, job_policy, ai_web_search, arbeitsagentur_source, himalayas_source, ats_urls
- `src/job_hunter_core/tracking/` — tracker (dedup), discovery_cache
- `src/job_hunter_core/linkedin/` — generate_ideas, draft_posts, discover_engagement, defaults.yml
- `config/` — all runtime behavior: search config, scoring weights, LLM provider settings
- `tests/` — pytest suite mirroring the src layout
- Docker-first deployment via `ghcr.io/jobhunterpath/job-hunter-core`

## Operating Rules

- Python handles all deterministic work: scraping, ATS, PDF compilation, state tracking, dedup.
- LLM handles judgment: scoring, tailoring, cover letter generation.
- Never hardcode personal data — all user-specific values live in `config/`.
- External I/O must have timeouts and log failures; no silent `except` blocks.
- Config-driven behavior — add new sources, providers, or output formats via config, not code rewrites.
- All imports use the `job_hunter_core.*` namespace (e.g., `from job_hunter_core.core.config import load_api_config`).
- Multi-provider LLM support: Anthropic (primary), OpenAI, Google, Ollama — provider selection is config-driven.

## Search Provider Architecture

- **Pre-flight gate**: `probe_search_providers()` at the top of `scrape()`. Fires a live test query against each enabled provider; any that fail or return 0 results are excluded for this run via `set_run_disabled()` — no file state read.
- **Source-first job fetching**: all enabled job-board sources (`JobSpySource`, `HimalayasSource`, `ArbeitsagenturSource`, etc.) are fetched in parallel per enabled region using `global_search.job_titles`. No per-company loop or per-company fallback.
- **ATS discovery** (once per run, global): `discover_ats_jobs_by_search(..., disabled=_run_disabled)`. Paid providers (Brave/Tavily/Exa) are used here; no restriction.
- **LLM job search** (optional, gated by `llm_job_search.enabled`): `fetch_ai_web_search_jobs()` uses the `ai_web_search` LLM role (Claude Haiku by default) to generate targeted queries when candidate count is below `trigger_threshold`.

## Dedup Architecture

- Persistent dedup is URL-only. `tracker.py` reads/writes only the `processed` key (list of URLs).
- `applied_titles` is removed from persistent state. Title-key dedup caused false positives and blank-metadata poisoning.
- In-run title-key dedup is intentionally absent from job-hunter-core. Use URL dedup only.

## Common Commands

```bash
job-hunter hunt [--region <key>] [--skip-score] [--skip-validate]   # scrape + score + tailor
job-hunter hunt --scrape-only [--region <key>]      # scrape + enrich snapshot only
job-hunter hunt --from-snapshot <path>              # score + tailor from scrape snapshot
job-hunter tailor-links --links <comma-separated-urls> [--skip-score] [--force]
job-hunter tailor-raw --jd <text> [--title] [--company] [--skip-score] [--force]
job-hunter merge-tracker               # merge dedup tracker state
job-hunter resolve-hunt-region         # resolve active region from config
job-hunter linkedin <generate-ideas|draft-posts|discover-networking|all> [--config]
job-hunter config check                # validate config files

python -m pytest tests/ -q --tb=short  # run test suite
```

## Skills

Skills live in `.claude/skills/<name>/SKILL.md`. The slash command is the directory name.

### Dev — contributor tools

| Skill | What it does |
|---|---|
| `/dev-code` | Python coding guidelines for `src/job_hunter_core/` |
| `/dev-refactor` | Safe refactoring protocol (imports, Dockerfile, pyproject.toml, tests) |
| `/dev-schema` | Config schema change protocol |
| `/dev-test` | Test conventions and patterns |
| `/dev-commit` | Pre-flight checks and commit message format |
