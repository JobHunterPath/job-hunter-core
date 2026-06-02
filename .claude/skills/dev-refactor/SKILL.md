---
name: dev-refactor
description: Safe structural refactoring guide for job-hunter-core — module renames, directory moves, import updates, and pyproject.toml package config changes.
when_to_use: Developer context only — when renaming modules, moving directories, updating package imports, or changing pyproject.toml package config.
user-invocable: true
allowed-tools: Bash Read Grep
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Structural Refactoring Guidelines

Apply these when renaming modules, moving directories, updating imports, or changing pyproject.toml package config in job-hunter-core.

Token rule: report only changed file paths, import counts, and test result. No full diffs.

## Before You Start

Grep all import patterns to find every file that will need updating. Focus on the top-level sub-packages:

```
from (core|discovery|linkedin|pipeline|sources|tracking)
```

Search both `src/` and `tests/`. Count the hits before touching anything so you know the full scope of the change.

Also check for string references to module names in `pyproject.toml`, `Dockerfile`, and any shell scripts in `scripts/`.

## Rename Steps

Complete these in order. Do not skip ahead.

1. Move or rename the files and directories.
2. Update all `import` and `from` statements in `src/` and `tests/` to reflect the new names.
3. Update `pyproject.toml`: check `tool.setuptools.packages.find` and any explicit `packages` lists.
4. Update Dockerfile `COPY` paths if the moved code is explicitly referenced.
5. Update any `__init__.py` re-exports that referenced the old location.

## After Rename

Run the full test suite before committing:

```
python -m pytest tests/ -q --tb=short
```

Tests must pass before the change is committed. If tests fail, diagnose the failure fully before continuing. A failing test suite is not a commit-ready state.

## Type Hints Addition

When adding type hints to existing code:

- Add `from __future__ import annotations` as the first non-comment line of each module being updated.
- Add return types and parameter types to all public functions (those not prefixed with `_`).
- Do not add type hints to private helpers in the same pass unless they are directly tested.
- Run `ruff check src/ tests/` after adding hints to catch annotation syntax errors early.

## Function Decomposition

If a function exceeds roughly 60 lines, it is a candidate for splitting:

- Split at clear responsibility boundaries, not at arbitrary line counts.
- Each resulting function should have a name that reads as a clear verb-noun: `fetch_job_listings`, `parse_html_response`, `write_tracking_record`.
- The original function may become a thin coordinator that calls the new ones.
- After splitting, run tests to confirm behavior is preserved.

## Never Break Tests

- Run tests after every non-trivial change, not just at the end.
- If a test fails mid-refactor, stop and diagnose before continuing.
- Do not comment out or delete tests to make a rename pass. Fix the tests to use the new names.
- A refactor that cannot pass the existing test suite without test deletions is not a safe refactor.

## Review Output

Report:

- List of changed file paths
- Total import statements updated (count only)
- Test result: pass count, fail count, or full error if tests fail

No full diffs. No file contents.
