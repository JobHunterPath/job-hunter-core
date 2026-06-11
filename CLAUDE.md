# job-hunter-core

Keep this file in sync with `AGENTS.md`.

You are working on the automation engine that powers the job search pipeline.

## Architecture

- `src/job_hunter_core/core/` — config loader, llm_client, utils, metrics, config_schema
- `src/job_hunter_core/pipeline/` — orchestrator, scorer, tailorer, cover_writer, enrichment, validator, pdf_compiler, readme_writer, company_registry, hunt_pipeline, tailor_pipeline
- `src/job_hunter_core/sources/` — ats, adzuna_source, reed_source, jobspy_source, job_boards, search_providers, jd_fetcher, job_policy, ai_web_search, arbeitsagentur_source, himalayas_source, ats_urls
- `src/job_hunter_core/discovery/` — discoverer (weekly company discovery)
- `src/job_hunter_core/tracking/` — tracker (dedup), discovery_cache
- `src/job_hunter_core/linkedin/` — generate_ideas, draft_posts, discover_engagement, defaults.yml
- `config/` — all runtime behavior: search config, scoring weights, LLM provider settings
- `tests/` — pytest suite mirroring the src layout
- Docker-first deployment via `ghcr.io/jobhunterpath/job-hunter-core`

## Operating Rules

- Python handles all deterministic work: scraping, ATS, PDF compilation, state tracking, dedup.
- LLM handles judgment: scoring, tailoring, cover letter generation, company discovery.
- Never hardcode personal data — all user-specific values live in `config/`.
- External I/O must have timeouts and log failures; no silent `except` blocks.
- Config-driven behavior — add new sources, providers, or output formats via config, not code rewrites.
- All imports use the `job_hunter_core.*` namespace (e.g., `from job_hunter_core.core.config import load_api_config`).
- Multi-provider LLM support: Anthropic (primary), OpenAI, Google, Ollama — provider selection is config-driven.

## Search Provider Architecture

- **Pre-flight gate**: `_run_disabled = get_exhausted_providers()` at the top of `scrape()`. Pass into all search calls for the entire run — never read `api_usage.json` inside per-company loops.
- **Per-company fallback**: `search_web(..., allowed={"searxng"}, disabled=_run_disabled)`. Paid APIs (Brave/Tavily/Exa) are restricted to the global ATS discovery phase only.
- **ATS discovery** (once per run, global): `discover_ats_jobs_by_search(..., disabled=_run_disabled)`. No `allowed` restriction here — paid providers are appropriate.

## Dedup Architecture

- Persistent dedup is URL-only. `tracker.py` reads/writes only the `processed` key (list of URLs).
- `applied_titles` is removed from persistent state. Title-key dedup caused false positives (same title at the same company months later) and poisoning (blank metadata producing a catch-all key blocking future jobs).
- In-run title-key dedup via in-memory `seen_titles` is intentionally absent from job-hunter-core (use URL dedup only). job-hunter retains it in `agent_context.py` for no-URL jobs only.

## Common Commands

```bash
job-hunter hunt [--region <key>] [--skip-score] [--skip-validate]   # scrape + score + tailor
job-hunter tailor-links --links <comma-separated-urls> [--skip-score] [--force]
job-hunter tailor-raw --jd <text> [--title] [--company] [--skip-score] [--force]
job-hunter discover                    # weekly company discovery
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
