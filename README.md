# Job Hunter Core

Open source job hunting automation engine.

## What it does

job-hunter-core scrapes jobs from 25+ sources (ATS APIs, job boards, AI-assisted search), scores them against your resume using an LLM, then tailors your resume and cover letter for each match. Runs as a Docker image triggered by GitHub Actions — no local Python setup needed.

## Architecture

    job-hunter-template (your fork)
        config/    search rules, scoring, LLM provider
        context/   your resume (.tex) and STAR story bank
             │
             ▼  GitHub Actions
    ghcr.io/jobhunterpath/job-hunter-core
        scrape → deduplicate → score (LLM) → tailor → PDF
             │
             ▼
        outputs/   tailored resume + cover letter

## Quick start

1. Click "Use this template" on [job-hunter-template](https://github.com/JobHunterPath/job-hunter-template)
2. Add your LLM API key as a GitHub secret (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GOOGLE_API_KEY`)
3. Edit `config/search_config.yml` — set your regions, target companies, job titles
4. Edit `context/resume_*.tex` with your resume and `context/story_bank.md` with your STAR stories
5. Run the `job_hunt` workflow from the Actions tab

## Supported sources

| Source | Type | Notes |
|---|---|---|
| Greenhouse | ATS API | Public jobs API |
| Lever | ATS API | Public jobs API |
| SmartRecruiters | ATS API | |
| Workable | ATS API | |
| Ashby | ATS API | |
| HiBob | ATS API | |
| Personio | ATS API | XML feed |
| Recruitee | ATS API | |
| Breezy | ATS API | |
| Teamtailor | ATS API | |
| Workday | ATS API | |
| Indeed | Job board | Via python-jobspy; no API key |
| Google Jobs | Job board | Via python-jobspy; no API key |
| Adzuna | Job board API | Requires API key |
| Reed | Job board API | Requires API key |
| JSearch | Job board API | Optional RapidAPI source; requires `RAPIDAPI_KEY` |
| Himalayas | Job board | Remote-focused |
| Remotive | Job board API | Free, no API key required |
| The Muse | Job board API | Free, no API key required |
| Bundesagentur für Arbeit | Job board | German market |
| Arbeitnow | Job board | |
| SearXNG | Search | Free local metasearch in GitHub Actions; uses simple per-site queries |
| Brave / Tavily / Exa | Search APIs | Optional keyed fallbacks with monthly budgets |
| Playwright | Browser renderer | Automatic JS-rendering fallback in the core image |
| Lightpanda | Fast renderer | Used automatically when the binary is present |
| Firecrawl | Cloud extraction | Used when `FIRECRAWL_API_KEY` and budget are available |
| AI web search | Search | LLM-assisted breadth source |
| MyCareersFuture | Job board | Singapore; free REST API; country: SG |
| EURES | Job board | 27 EU + NO/IS/LI; public REST API; any EU/EEA country |
| Job Bank Canada | Job board | Canada; HTML scrape; country: CA |
| Welcome to the Jungle | Job board | Global / EU-heavy; free JSON API |
| Glints | Job board | SEA (SG, ID, MY, VN, PH); REST JSON; country: SG/ID/MY/VN/PH |
| IrishJobs | Job board | Ireland; HTML scrape; country: IE |
| GulfTalent | Job board | Gulf (AE, SA, QA, KW, BH, OM); requests → Playwright fallback |
| Naukrigulf | Job board | Gulf (AE, SA, QA, KW, BH, OM); requests → Playwright fallback |
| JobStreet | Job board | SEA (SG, MY, ID, PH, VN); REST API → Playwright fallback |

## Configuration

All configuration lives in `config/`. See `config/templates/` for commented examples and [SETUP.template.md](SETUP.template.md) for full setup instructions.

## Terms of Service notice

> **ToS Notice**: ATS APIs (Greenhouse, Lever, etc.) are publicly documented and safe to use. Other sources (Indeed, Google Jobs) are accessed via [python-jobspy](https://github.com/speedyapply/JobSpy) — a widely used open source library. Users are solely responsible for compliance with applicable terms of service, laws, and regulations. The authors provide no warranty and accept no liability.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
