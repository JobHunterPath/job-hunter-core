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

## SOLID Scope

Only enforce S and O from SOLID:

- **Single Responsibility:** each module, class, and function should have one clear reason to change. Split code that mixes unrelated jobs such as scraping, parsing, config loading, file writing, or presentation formatting.
- **Open/Closed:** add new providers, ATS handlers, config keys, or output formats through small extension points and config-driven choices instead of risky rewrites of existing behavior.

Prefer the simplest readable code that fits the existing package shape.

## Python Automation Guidelines

- Follow PEP 8 in spirit: clear names, readable control flow, small cohesive functions, and boring code over clever abstractions.
- Keep reusable Python generic. Personal names, target titles, role preferences, locations, thresholds, and application targeting belong in `config/`, not in `src/job_hunter_core/`.
- Put user-tunable values in config. Use named constants only for internal protocol details, formatting limits, or values users should not normally tune.
- Keep deterministic work in Python. Python may scrape, import, normalize, compile PDFs, update tracking, and write deterministic summaries. There is no agent skill system in job-hunter-core — judgment work belongs to the consuming agent layer.
- Make external I/O explicit. Network, browser, subprocess, and filesystem-heavy operations should have clear boundaries, timeouts where applicable, and tests that can mock those boundaries.
- Log useful context around external failures and intentionally swallowed exceptions. Avoid silent `except` blocks.
- Keep CLI behavior honest. Do not add flags that do nothing, hide backend behavior, or imply unsupported automation. Use `argparse` defaults and exit behavior consistently.
- Use structured parsers for YAML and JSON. Prefer `pathlib` for filesystem paths and explicit UTF-8 for text files.
- Avoid compatibility shims, dead code, and comments that restate the code. Comments should explain non-obvious why, not ordinary what.
- Preserve the canonical package layout: importable code lives under `src/job_hunter_core/`, and imports should use `job_hunter_core.*`.
- Require type hints on all public functions. Add `from __future__ import annotations` at the top of every module that uses them.

## Multi-Provider LLM Guidelines

job-hunter-core supports Anthropic, OpenAI, Google, and Ollama. Apply these rules when touching LLM integration code:

- Route provider selection through config, never through hard-coded conditionals scattered across modules.
- Each provider adapter should implement the same interface; new providers are added by extending that interface, not by modifying existing adapters.
- Never import a provider SDK at module level if it may not be installed. Use lazy imports or optional dependency guards.
- Keep provider-specific retry logic, rate-limit handling, and auth inside the adapter, not in the calling code.

## Docker-First Deployment Guidelines

- The deployment target is Docker; do not add system-level dependencies that are not installable via `pip` or already present in the base image.
- Do not read from `~/.config`, `~/.local`, or other user-home paths that will not exist inside a container. Read all config from paths relative to the project root or from environment variables.
- Environment variables are the canonical way to pass secrets and runtime overrides into the container. Never hard-code credentials or paths that differ between environments.
- If a new external tool or binary is required, note the Dockerfile change needed alongside the code change.

## Testing Guidelines

- Add or update tests for new public behavior and changed config keys.
- Mock network, browser, subprocess, and external service calls at the point of use.
- Keep fixtures small, deterministic, and local to the test unless reuse is valuable.
- Prefer testing observable behavior over private implementation details.
- Run `python -m pytest tests/ -q --tb=short` before committing code changes.
- Run `ruff check src/ tests/` to catch lint issues before committing.

## Review Output

For each finding, report:

- `file:line`
- guideline category
- smallest safe fix

End with `GO` if no blocking issues remain, otherwise `NEEDS-WORK`.
