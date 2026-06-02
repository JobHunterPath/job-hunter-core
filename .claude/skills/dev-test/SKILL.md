---
name: dev-test
description: Test patterns and conventions for job-hunter-core — where tests live, how to run them, mocking external calls, and what to cover.
when_to_use: Developer context only — use when modifying repo code, not during job search. Triggered when user asks to run tests or write tests, or after a code change in src/job_hunter_core/ needs verifying.
user-invocable: true
allowed-tools: Bash Read
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Testing

Token rule: report the command, pass/fail count, and short failure trace only. Do not paste full logs for passing tests.

## Run

```
python -m pytest tests/ -q --tb=short
```

## Conventions

- Tests live in `tests/test_*.py`, mirroring `src/job_hunter_core/` layout (e.g., `tests/test_ats.py` for `sources/ats.py`).
- Mock all external I/O with `unittest.mock.patch`: HTTP requests, LLM API calls, Playwright browser, subprocess, filesystem writes. Tests must never hit the network or call real LLM APIs.
- Patch at the point of use. For functions imported inside a function body, patch the source module (e.g. `job_hunter_core.sources.search_providers.SomeClass`), not the caller.
- Use small inline fixtures (dicts) for config, not live `config/*.yml`. Tests must not depend on real user data.
- Test public functions in `src/job_hunter_core/`. Skip trivial private helpers unless the logic is non-obvious.
- Parametrize filter and policy tests — `job_policy.py` rules (title, location, language, industry, stale) are a natural fit for table-driven cases.
- LLM tests: mock the LLM client to return minimal fixture JSON; never call Anthropic/OpenAI/Google in tests.

## What to cover

- Every new public function gets at least one test.
- For a bug fix, add the test that would have caught it.
- For filter/policy logic, test both the accept and reject path.
- For a new source (job board or ATS), test: successful parse, empty result, HTTP error, malformed response.
- For config changes, assert the new key is read and falls back to a sensible default when absent.

## conftest.py

`tests/conftest.py` creates a minimal `config/api_config.yml` in a temp directory and sets `JOB_HUNTER_ROOT` to point at it. All tests that need config inherit this fixture. Do not add heavyweight shared state — keep conftest minimal.

## Before committing

Tests must pass. A failure blocks the commit unless the user explicitly accepts the failure.
