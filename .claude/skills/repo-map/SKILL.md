---
name: repo-map
description: Print a compact source map of job-hunter-core — package layout, entry points, current refactor phase, and LOC per module.
when_to_use: Developer context only — use when orienting in the codebase, reviewing phase status, or planning structural changes.
user-invocable: true
allowed-tools: Bash Read Glob
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Repo Map

Run `python .claude/skills/repo-map/scripts/print_map.py` from `job-hunter-core/` to see the current package layout with LOC counts.

## Canonical Package Layout (post-Phase-4 refactor)

```
src/job_hunter_core/
  core/               config, api_budget, utils, llm_client, llm_utils
  sources/
    ats/              __init__, _base, dispatch, greenhouse, lever, smartrecruiters,
                      workable, ashby, hibob, personio, recruitee, breezy, teamtailor, workday
    career_pages/     __init__, _ats_patterns, _jsonld, _sitemap, _rendering, _ladder
    scraper/          __init__, _stats, _config, _policy
    search_providers/ __init__, _constants, _result, _url_utils, providers, router,
                      ats_discovery, fetchers, discovery
    *_source.py       one file per job board (adzuna, himalayas, reed, …)
  pipeline/           scorer, tailorer, cover_writer, validator, enrichment, pdf_compiler
  tracking/           tracker, discovery_cache
  discovery/          discoverer
  linkedin/           common, draft, engagement
```

## Entry Points

| Function | Module |
|---|---|
| `scrape()` | `sources/scraper/__init__.py` |
| `fetch_ats_jobs()` | `sources/ats/__init__.py` |
| `search_web()` | `sources/search_providers/router.py` |
| `discover_ats_jobs_by_search()` | `sources/search_providers/ats_discovery.py` |
| `extract_career_page_jobs()` | `sources/career_pages/_ladder.py` |

## Refactor Phase Status

| Phase | Status |
|---|---|
| 1 — ruff config | complete |
| 2 — typed models (JobPosting, Company) | complete |
| 3 — JobSourceAdapter ABC | complete |
| 4 — package splits (search_providers, ats, career_pages, scraper) | complete |
| 5 — named constants | complete |
| 6 — skills | complete |

See `dev-refactor` for split patterns and rules.
