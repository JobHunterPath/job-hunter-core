# Contributing

Contributions are welcome. Please read this document before opening a PR.

## Getting started

1. Fork the repo and clone your fork.
2. Install in editable mode with dev dependencies (Python 3.11+):
   ```
   pip install -e ".[dev]"
   ```
3. Run the test suite:
   ```
   python -m pytest tests/ -q --tb=short
   ```
4. Lint your changes:
   ```
   ruff check src/ tests/
   ```

## Contribution workflow

1. **Open an issue first** — describe the bug or feature before writing code. This avoids duplicate work and lets maintainers flag design concerns early.
2. **Create a feature branch from `main`**:
   ```
   git checkout -b feat/your-feature-name
   ```
3. **Open a PR** — all required checks (tests + lint) must pass before review.

## Adding a new job source

1. Create `src/job_hunter_core/sources/<name>_source.py` following the interface of an existing source.
2. Register the source in `src/job_hunter_core/sources/scraper.py`.
3. Add `tests/test_<name>_source.py` with mocked HTTP calls — no live network calls in tests.
4. Add a row for the new source to the **Supported sources** table in `README.md`.

## Config changes

- **Adding a key**: update `config/templates/`, `config/schemas/`, `README.md`, and `SETUP.template.md` in the same commit.
- **Removing or renaming a key**: this is a breaking change. Note it explicitly in the PR description.

## Code style

- `ruff check src/ tests/` must pass with no errors.
- Type hints are required on all public functions.
- No silent `except` blocks — catch specific exceptions and log or re-raise.
- Commit messages: one-line subject, imperative mood:
  ```
  feat(sources): add arbeitsagentur source
  fix(scoring): handle empty JD response from LLM
  docs: update SETUP.template.md prerequisites
  ```
  Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `chore`
