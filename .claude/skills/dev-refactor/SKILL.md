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

Search both `src/` and `tests/`. Also check string references in `pyproject.toml`, `Dockerfile`, and scripts.

For detailed rename steps, type hints addition, and function decomposition guidance, see `dev-refactor/reference.md`.

## Never Break Tests

- Run `python -m pytest tests/ -q --tb=short` after every non-trivial change.
- If a test fails mid-refactor, stop and diagnose before continuing.
- Do not comment out or delete tests to make a rename pass.

## Review Output

Report:

- List of changed file paths
- Total import statements updated (count only)
- Test result: pass count, fail count, or full error if tests fail

No full diffs. No file contents.

## Package Splits

When splitting a flat `.py` file into a `<dir>/` package:

1. Create `<dir>/__init__.py` that re-exports every public name from the old file.
2. Move content to sub-files; keep the shim intact until all internal callers are updated.
3. `grep -rn "from job_hunter_core.sources.<old_name>"` must return zero hits before removing the shim.
4. Never remove the shim in the same commit that moves code.
5. For test patch compatibility: if `patch("pkg.mod.fn", ...)` was used before the split, the function being called must either (a) remain in `__init__.py`, or (b) be patched at the sub-module where it is looked up at call time.
6. Integers re-exported from `__init__.py` are copies — patching them on `__init__` does not update sub-module bindings. Dicts and Locks are references — safe to re-export and patch.
