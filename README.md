# Job Hunt Automation Template

Automated job discovery across multiple locations, fit scoring, resume tailoring, cover letter generation, and PDF output. The scraper uses direct ATS APIs, HTTP/BeautifulSoup, Playwright, an ephemeral SearXNG container in GitHub Actions, optional AI web search by job title and region, and optional search APIs (Brave, Tavily, Exa).

Also includes a lightweight LinkedIn content system: generates public-safe post ideas from your private story bank, creates weekly draft posts for review, and suggests people/posts for manual engagement. It never posts, comments, connects, messages, or likes automatically.

## Start Here

Read [SETUP.md](SETUP.md) for full step-by-step setup — including how to fill in your story bank, build a resume, configure job search, grant core image access, and run the automation.

When using AI helpers in VS Code, use them only for personal files: story bank, resume, project instructions, and configs. Do not ask them to modify workflows or automation-owned files. Code fixes come through the maintained private core and template.

For future updates, run **Actions → Update From Template** in your own repo. It creates a merge commit that imports the latest maintained template files into your selected branch while keeping your resume, story bank, generated jobs, and configs untouched by default. The workflow summary shows whether the update is a patch, minor, or major change. After it finishes, run `git pull origin main` locally.

## Quick Start

1. Fill in `project_instructions.md` with your profile, ID scheme, and chatbot prompts.
2. Fill in `story_bank.md` with verified STAR stories from your experience.
3. Choose and customize a resume: `resume_double_column.tex` (AltaCV layout) or `resume_single_column.tex` (ATS-friendly).
4. Update all files under `config/` — especially `api_config.yml`, `search_config.yml`, `scoring_config.yml`, `cover_letter_config.yml`, and `tailoring_config.yml`.
5. In `config/api_config.yml`, set `profile.resume_tex`, `profile.story_bank`, and `profile.project_instructions`.
6. Add required GitHub secrets (at minimum your LLM provider key; see table below).
7. Add `CORE_IMAGE_PAT` if prompted — needed to pull the private core image.
8. Commit, push, and enable workflows under the **Actions** tab.

Scheduled hunts run the primary enabled region every weekday. Secondary enabled regions run Monday, Wednesday, and Friday. Manual **Job Hunt Pipeline** runs accept `all` or a specific region key from `config/search_config.yml`.

**Project section tailoring:** When your resume has an uncommented Projects section, the tailorer selects and adjusts project content from your story bank to match each job. It will never uncomment a commented-out section. Configure allowed story ID prefixes, project count, and bullet limits in `config/tailoring_config.yml` under `tailoring.rules.projects`.

## Secrets and Providers

| Secret | Provider / Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic (LLM) |
| `OPENAI_API_KEY` | OpenAI (LLM) |
| `GOOGLE_API_KEY` | Google Gemini (LLM) |
| `BRAVE_API_KEY` | Brave Search (optional fallback) |
| `TAVILY_API_KEY` | Tavily Search (optional fallback) |
| `EXA_API_KEY` | Exa Search (optional fallback) |
| `RAPIDAPI_KEY` | JobSpy / Indeed (optional) |
| `CORE_IMAGE_PAT` | Pull the private core image from GHCR |
| `GH_PAT` | Allow workflows to commit results back to your repo |
| `TEMPLATE_REPO_PAT` | Read the template repo for Update From Template |

Set `secrets.<provider>.required: true` only for providers you actually use in `config/api_config.yml`.

GitHub Actions starts SearXNG temporarily for each hunt and discovery run. If SearXNG or any API provider fails, the pipeline continues with the next available option.

## Local Run

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/job-network-projects/job-hunter-core:latest \
  job-hunter hunt
```

For direct job URLs:

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/job-network-projects/job-hunter-core:latest \
  job-hunter tailor-links --links "https://example.com/job"
```

## Outputs

Generated application files are written to `jobs/YYYY-MM-DD_company_role/`.

LinkedIn review files are written to `linkedin/ideas.md`, `linkedin/drafts/`, `linkedin/engagement.md`, and `linkedin/networking.md`. Review everything manually before using it on LinkedIn.

The tracker in `config/applied_jobs.yml` prevents duplicate processing. Each hunt run tailors at most 15 matched jobs, highest-scoring first.

## Applied Jobs

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
<!-- JOBS_TABLE_END -->
