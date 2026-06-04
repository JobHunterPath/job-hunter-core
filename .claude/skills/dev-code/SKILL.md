---
name: dev-code
description: Python coding guidelines for the job-hunter-core src/job_hunter_core package, focused on simple SOLID usage, Python automation practices, and this repo's multi-provider Docker-first architecture.
when_to_use: Developer context only — use when writing or reviewing Python code in src/job_hunter_core/ or updating repo coding standards.
user-invocable: true
allowed-tools: Bash Read Grep
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Coding Guidelines

Apply these when writing or reviewing Python in `src/job_hunter_core/`.

Token rule: report only findings with file, line, category, and smallest safe fix. Do not paste full diffs or full files.

For Docker deployment rules and testing guidelines, see `dev-code/reference.md`.

## SOLID Scope

Only enforce S and O from SOLID:

- **Single Responsibility:** each module, class, and function should have one clear reason to change. Split code that mixes unrelated jobs such as scraping, parsing, config loading, file writing, or presentation formatting.
- **Open/Closed:** add new providers, ATS handlers, config keys, or output formats through small extension points and config-driven choices instead of risky rewrites of existing behavior.

Prefer the simplest readable code that fits the existing package shape.

## Python Automation Guidelines

- Follow PEP 8 in spirit: clear names, readable control flow, small cohesive functions, and boring code over clever abstractions.
- Keep reusable Python generic. Personal names, target titles, role preferences, locations, thresholds, and application targeting belong in `config/`, not in `src/job_hunter_core/`.
- Put user-tunable values in config. Use named constants only for internal protocol details, formatting limits, or values users should not normally tune.
- Keep deterministic work in Python. Judgment work belongs to the consuming agent layer.
- Make external I/O explicit. Network, browser, subprocess, and filesystem-heavy operations should have clear boundaries, timeouts where applicable, and tests that can mock those boundaries.
- Log useful context around external failures and intentionally swallowed exceptions. Avoid silent `except` blocks.
- Use structured parsers for YAML and JSON. Prefer `pathlib` for filesystem paths and explicit UTF-8 for text files.
- Preserve the canonical package layout: importable code lives under `src/job_hunter_core/`, imports use `job_hunter_core.*`.
- Require type hints on all public functions. Add `from __future__ import annotations` at the top of every module that uses them.

## Multi-Provider LLM Guidelines

job-hunter-core supports Anthropic, OpenAI, Google, and Ollama. Apply these rules when touching LLM integration code:

- Route provider selection through config, never through hard-coded conditionals scattered across modules.
- Each provider adapter should implement the same interface; new providers are added by extending that interface.
- Never import a provider SDK at module level if it may not be installed. Use lazy imports or optional dependency guards.
- Keep provider-specific retry logic, rate-limit handling, and auth inside the adapter, not in the calling code.

## Token Efficiency for Skills

When writing or editing a dev skill:

- **Size target:** keep `SKILL.md` under 60 lines. If over, extract to `reference.md`.
- Move YAML schemas, markdown templates, step sequences, and enumerated rule lists to `reference.md`. The skill instructs Claude to read it; don't embed the detail inline.
- No repeated rules: if a rule already lives in `CLAUDE.md` or another skill, reference it — don't copy it.
- For Python LLM callers: use `cache_system=True, cache_ttl="5m"` for parallel calls (scorer), `cache_ttl="1h"` for sequential calls that span >5 minutes (tailorer, cover_writer). Build system prompts from stable config-driven content; keep per-job variable fields in the user message.

## Review Output

For each finding, report:

- `file:line`
- guideline category
- smallest safe fix

End with `GO` if no blocking issues remain, otherwise `NEEDS-WORK`.
