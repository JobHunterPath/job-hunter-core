---
name: source-adapter
description: Step-by-step guide for adding a new job board or ATS adapter to job-hunter-core, including subclassing JobSourceAdapter, wiring dispatch, and writing tests.
when_to_use: Developer context only — use when adding a new job source to job-hunter-core.
user-invocable: true
allowed-tools: Bash Read Grep
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Adding a New Source Adapter

Run `python .claude/skills/source-adapter/scripts/validate_adapter.py <module.ClassName>` to validate a new adapter before committing.

## Steps

1. **Create** `src/job_hunter_core/sources/<platform>_source.py`
2. **Subclass** `JobSourceAdapter` from `job_hunter_core.sources.base` — see `scripts/template.py` for a minimal skeleton.
3. **Register** in `scraper/__init__.py` imports and dispatch
4. **Write tests** covering: successful parse, empty response, HTTP error, malformed response
5. **Validate**: `python .claude/skills/source-adapter/scripts/validate_adapter.py job_hunter_core.sources.myplatform_source.MyPlatformSource`

## Contract

- `fetch()` must never raise — catch all exceptions and return `[]`
- Each returned dict must have: `title`, `company`, `url`, `location`, `snippet`, `source`, `posted`
- `is_enabled(config)` defaults to `True` — override to check config flags
