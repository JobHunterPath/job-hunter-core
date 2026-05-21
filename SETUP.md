# Setup Guide

This repository is your personal job-hunt workspace. It stores your resume,
story bank, project instructions, config files, workflow files, and generated
outputs. The automation code runs from a maintained private core image, so this
template does not need to carry Python scripts, tests, package files, or a
Dockerfile.

## 1. Install The Required Apps

Install:

- Git from `https://git-scm.com/downloads`
- Visual Studio Code from `https://code.visualstudio.com/`
- Docker Desktop from `https://www.docker.com/products/docker-desktop/`

Open Docker Desktop once and wait until the Docker engine is running.

## 2. Create Your Private Repository

1. Open the shared template repository on GitHub.
2. Click **Use this template**.
3. Choose **Create a new repository**.
4. Set visibility to **Private**.
5. Create the repository.

Your new repository is your personal workspace. Keep it private because it will
contain resume material, story-bank details, generated job artifacts, and API
configuration.

## 3. Clone Your Repository

In VS Code, use **Source Control -> Clone Repository**, or run:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
code .
```

Configure Git if this is a new machine:

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## 4. Use AI Helpers Only For Personal Files

Claude Code, Codex, Copilot, or another local AI helper can help you edit:

- `project_instructions.md`
- `story_bank.md`
- resume `.tex` files
- files under `config/`
- files under `linkedin/`

Do not ask an AI helper in your personal repo to change workflows or automation
internals. The maintained core code lives outside this repo.

## 5. Fill In Your Source Material

Before running automation, complete these files:

- `project_instructions.md`
- `story_bank.md`
- `resume_single_column.tex` or `resume_double_column.tex`
- `config/api_config.yml`
- `config/search_config.yml`
- `config/scoring_config.yml`
- `config/cover_letter_config.yml`
- `config/tailoring_config.yml`

In `config/api_config.yml`, confirm that `profile.resume_tex`,
`profile.story_bank`, and `profile.project_instructions` point to the files you
actually use.

## 6. Configure API Keys

Choose one primary LLM provider in `config/api_config.yml`, then add the matching
GitHub secret:

| Provider | GitHub Secret |
|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `google` | `GOOGLE_API_KEY` |

Optional search providers use these secrets:

| Provider | GitHub Secret |
|---|---|
| Brave | `BRAVE_API_KEY` |
| Tavily | `TAVILY_API_KEY` |
| Exa | `EXA_API_KEY` |
| RapidAPI / JobSpy | `RAPIDAPI_KEY` |

Add secrets in **Settings -> Secrets and variables -> Actions -> New repository
secret**.

Set `secrets.<provider>.required: true` only for providers you actually use.

## 7. Grant Access To The Private Core Image

The workflows pull this maintained image by default:

```text
ghcr.io/abdulrbasit/abdul.basit_resume/job-hunter-core:latest
```

For GitHub Actions to pull it, use one of these options:

- Preferred: the maintainer grants your repository package access in GHCR.
- Alternative: add a `CORE_IMAGE_PAT` repository secret with package read access.

If access is missing, the workflow fails early with an image-pull error instead
of trying to install code locally.

You can override the image with a repository variable:

```text
JOB_HUNTER_CORE_IMAGE=ghcr.io/OWNER/REPO/job-hunter-core:tag
```

## 8. Configure Repository Update Tokens

Most daily workflows can commit with GitHub's built-in `GITHUB_TOKEN` when your
repository allows Actions write access. For stricter repositories, add:

```text
GH_PAT
```

Use a fine-grained GitHub personal access token scoped only to this repository
with **Contents: Read and write**. Add **Workflows: Read and write** if you want
to run **Update From Template**, because that workflow updates files under
`.github/workflows/`.

The upstream template is private, so future template updates also need:

```text
TEMPLATE_REPO_PAT
```

Create it from an account that can read `Job-Network-Projects/job-hunter-template`
and grant **Contents: Read-only**.

## 9. Optional Local Smoke Test

After package access is configured, you can test the config locally with Docker.

PowerShell:

```powershell
docker login ghcr.io
docker run --rm `
  -e JOB_HUNTER_ROOT=/workspace `
  -v "${PWD}:/workspace" `
  -w /workspace `
  ghcr.io/abdulrbasit/abdul.basit_resume/job-hunter-core:latest `
  job-hunter config check
```

Bash:

```bash
docker login ghcr.io
docker run --rm \
  -e JOB_HUNTER_ROOT=/workspace \
  -v "$PWD:/workspace" \
  -w /workspace \
  ghcr.io/abdulrbasit/abdul.basit_resume/job-hunter-core:latest \
  job-hunter config check
```

## 10. Commit And Push Your Setup

GitHub Actions only sees files that have been pushed.

```bash
git status
git add .
git commit -m "complete initial job hunt setup"
git push origin main
```

If Git says `nothing to commit`, continue.

## 11. Run The Automation In GitHub

Open the **Actions** tab in your repository. Enable workflows if GitHub asks.

Common workflows:

- **Job Hunt Pipeline** searches configured regions and generates job artifacts.
- **Tailor Links** tailors your resume and cover letter for one or more job URLs.
- **Tailor Raw JD** tailors from a pasted job description.
- **LinkedIn Content** creates private draft ideas and engagement suggestions.
- **Update From Template** imports maintained template changes.

Scheduled weekday hunts run the primary enabled region. Secondary enabled
regions run on their configured weekday slots. Empty slots exit before expensive
pipeline work.

## 12. Pull Future Template Updates

Run **Actions -> Update From Template** in your personal repo. After it finishes,
run locally:

```bash
git pull origin main
```

Template updates should preserve personal files such as your resume, story bank,
generated jobs, and config values unless a migration explicitly says otherwise.

## Troubleshooting

If a workflow cannot pull the core image, confirm package access or add
`CORE_IMAGE_PAT`.

If a workflow says an LLM provider key is missing, confirm both the GitHub secret
and the matching `config/api_config.yml` provider setting.

If generated PDFs are missing, check the workflow logs and uploaded `job_hunt.log`
artifact first. The core image already includes LaTeX and Playwright.
