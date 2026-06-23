# Job Hunter Core

> **This repository is archived.** Development has moved to [abdulrbasit/job-hunter](https://github.com/abdulrbasit/job-hunter).

Open-source engine behind the job-hunt template. It scrapes jobs, deduplicates URLs, enriches job descriptions, validates fit, scores with an LLM, tailors resumes and cover letters, compiles PDFs, updates the README job table, and tracks processed URLs.

## User View

Most users should start from [job-hunter-template](https://github.com/JobHunterPath/job-hunter-template), not this repo. The template keeps personal config and outputs; this repo publishes the Docker image and maintained template files.

The template workflow runs:

1. Resolve the active region.
2. Start SearXNG.
3. Run `job-hunter hunt --scrape-only` to scrape, URL-check, enrich, and write `outputs/state/hunt_scrape_<date>_<region>.json`.
4. Run `job-hunter hunt --from-snapshot <path>` only when candidates exist.
5. Commit generated job outputs.

Company order is shuffled on every scrape so long lists get fair coverage across timed GitHub Actions runs.

## Developer View

Important package areas:

| Path | Purpose |
|---|---|
| `src/job_hunter_core/sources/` | ATS, career-page, job-board, search-provider, and JD fetchers |
| `src/job_hunter_core/pipeline/` | Hunt orchestration, scoring, tailoring, validation, PDF, README, tracker flow |
| `src/job_hunter_core/core/` | Config, schema checks, LLM client, metrics, URL liveness |
| `config/templates/` | Template defaults copied into user repos |
| `.github/template-workflows/` | Workflows copied into the public template |
| `README.template.md`, `SETUP.template.md` | User-facing template docs |

Template generation:

```bash
python .github/scripts/build_template_repo.py ../job-hunter-template
```

Do not hand-edit `job-hunter-template/` for maintained files; update the source here and rebuild/sync.

## CLI

```bash
job-hunter hunt [--region primary]
job-hunter hunt --scrape-only [--region primary]
job-hunter hunt --from-snapshot outputs/state/hunt_scrape_YYYY-MM-DD_primary.json
job-hunter tailor-links --links "https://example.com/job"
job-hunter tailor-raw --jd "..." --title "Product Manager" --company "Acme"
job-hunter config check
```

`--scrape-only` and `--from-snapshot` are mutually exclusive. Empty scrape results are successful runs and emit `candidate_count=0`.

## Sources

The engine combines public ATS APIs, configured company career pages, static HTML, Lightpanda/Playwright rendering, SearXNG, JobSpy, free job boards, optional keyed APIs, and optional AI web search. Paid search APIs are reserved for global ATS discovery, not per-company fallback.

Removed sources should be deleted from code, schemas, config templates, docs, and tests together.

## Checks

```bash
python -m pytest tests/ -q --tb=short
python -m ruff check src/ tests/
python -c "import yaml, pathlib; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('.github/template-workflows').glob('*.yml')]; print('workflow yaml ok')"
```

## Safety

- Never hardcode personal data in `src/`.
- Never fabricate resume facts, metrics, dates, credentials, employers, or outcomes.
- Keep external actions draft-only; this project does not submit applications or send messages.

MIT license. See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution details.
