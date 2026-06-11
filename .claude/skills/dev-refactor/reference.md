# Dev-Refactor Reference

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

Tests must pass before the change is committed. A failing test suite is not a commit-ready state.

## Type Hints Addition

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
