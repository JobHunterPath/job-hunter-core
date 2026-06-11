# Job Hunt Automation Template

Private workspace for your automated job search. GitHub Actions finds jobs, scores fit, tailors resumes and cover letters, compiles PDFs, and commits the results back to this repo.

## Start Here

1. Read [SETUP.md](SETUP.md).
2. Add your resume, story bank, search config, and API keys.
3. Run **Actions -> Job Hunt** once.
4. Review generated files in `jobs/` before applying anywhere.

The automation never submits applications, sends messages, posts, comments, likes, follows, or connects for you.

## What Runs

- **Job Hunt**: scrapes a region, writes an intermediate scrape snapshot, then scores/tailors only if candidates were found. Company order is shuffled each run so long company lists get fair coverage.
- **Company Discovery**: manual workflow for finding more target company career pages.
- **Tailor From Links / Raw JD**: manual workflows for specific jobs you already found.
- **Update From Template**: imports maintained workflow, config, and doc updates while preserving your personal files and config values.
- **LinkedIn Content**: optional, disabled by default, draft-only.

## Main Files

| Path | Purpose |
|---|---|
| `config/search_config.yml` | Regions, companies, target job titles, exclusions |
| `config/scoring_config.yml` | Fit threshold and seniority rules |
| `config/tailoring_config.yml` | Resume tailoring rules |
| `config/cover_letter_config.yml` | Cover letter tone and background |
| `config/api_config.yml` | LLM/search providers, budgets, source toggles |
| `context/` | Your resume source files and story bank |
| `jobs/` | Tailored job outputs |
| `config/applied_jobs.yml` | Processed URL tracker |

## Job Sources

Default runs use no paid search key. The pipeline checks configured company career pages, public ATS APIs, SearXNG, JobSpy, and free job boards first. Optional keyed providers such as Brave, Tavily, Exa, Adzuna, Reed, Jooble, JSearch, and Firecrawl add breadth when configured.

Every result is deduplicated, URL-checked, enriched with the full job description when possible, validated, scored, and only then tailored. Each hunt tailors at most the 15 highest-scoring matches.

## Daily Use

- Run **Job Hunt** manually or let the schedule run.
- Check the workflow summary and uploaded `job_hunt.log` if results look thin.
- Review every generated resume and cover letter before using it.
- Run **Update From Template** when updates are announced.

## Local Run

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/jobhunterpath/job-hunter-core:latest \
  job-hunter hunt
```

For setup, keys, troubleshooting, schedules, and optional LinkedIn workflows, use [SETUP.md](SETUP.md).

## Applied Jobs

<!-- JOBS_STATS_START -->
No jobs tracked yet.
<!-- JOBS_STATS_END -->

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
<!-- JOBS_TABLE_END -->
