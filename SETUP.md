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

1. Open the shared template repository on GitHub. Use the link provided to you
   by the maintainer — it will look like
   `https://github.com/Job-Network-Projects/job-hunter-template`.
2. Click **Use this template** (green button, top right).
3. Choose **Create a new repository**.
4. Set visibility to **Private**.
5. Give it any name you like (e.g. `my-job-hunt`).
6. Click **Create repository**.

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

## 4. Fill In Your Source Material

The automation works from four personal files you must complete before running
any workflow. Open each file in VS Code and replace the placeholder content.

**`project_instructions.md`** — the AI's primary reference for everything it
generates. Fill in:
- Your target roles, seniority level, and preferred locations
- Industries and company types you want to work in
- Industries, roles, or companies to exclude
- Your job ID naming scheme (used for output folder names)
- Tone and style preferences for cover letters

**`story_bank.md`** — raw material the AI draws from when writing cover letters
and tailoring resume bullets. Add:
- One section per role or project in your history
- Key achievements written as rough STAR notes (Situation, Task, Action, Result)
- Numbers and metrics wherever you have them — the AI will not invent them

**`resume_single_column.tex`** or **`resume_double_column.tex`** — your base
LaTeX resume. The pipeline creates a tailored copy for each job without touching
this file. Fill in your real experience, education, and skills. The AI will
adjust wording and reorder bullets but will never add content that is not
already in your resume or story bank.

**`config/`** — configure the search and scoring behaviour:
- `search_config.yml`: target companies, regions, and job titles to search
- `scoring_config.yml`: minimum fit score and maximum years of experience
- `cover_letter_config.yml`: your background summary and cover letter tone
- `tailoring_config.yml`: what the AI is allowed to change in your resume
- `api_config.yml`: set `profile.resume_tex`, `profile.story_bank`, and
  `profile.project_instructions` to point at the files you actually use

## 5. Use An AI Helper To Fill In Personal Files

An AI coding assistant in VS Code can speed up filling in the files above
significantly. Recommended options:

- **Claude Code** — install the VS Code extension or CLI from Anthropic's docs,
  then open a conversation in your repo folder
- **GitHub Copilot** — install the GitHub Copilot extension and sign in
- **Codex** — install Node.js, then run `npm install -g @openai/codex`

Use the AI helper to draft your `project_instructions.md`, populate
`story_bank.md` from your CV or LinkedIn, and fill in config files. It can see
your files and preserve their exact format.

Only use AI helpers for your personal files listed above. Do not ask them to
edit workflow files, scripts, or anything under `.github/` — those are
maintained centrally and your changes would be overwritten by the next update.

## 6. Configure API Keys

The pipeline needs at least one LLM provider key to score jobs and write cover
letters.

**Get an API key** from one of these providers:

| Provider | Sign-up page | GitHub Secret name |
|---|---|---|
| Anthropic (recommended) | `https://console.anthropic.com` → API Keys | `ANTHROPIC_API_KEY` |
| OpenAI | `https://platform.openai.com/api-keys` | `OPENAI_API_KEY` |
| Google | `https://aistudio.google.com/apikey` | `GOOGLE_API_KEY` |

Optional job-search providers (add only the ones you use):

| Provider | GitHub Secret name |
|---|---|
| Brave Search | `BRAVE_API_KEY` |
| Tavily | `TAVILY_API_KEY` |
| Exa | `EXA_API_KEY` |
| RapidAPI / JobSpy | `RAPIDAPI_KEY` |

**Add each key as a GitHub secret:**

1. In your repository, click **Settings** (top menu bar).
2. In the left sidebar click **Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Enter the secret name (e.g. `ANTHROPIC_API_KEY`) and paste your key as the
   value.
5. Click **Add secret**.

**Tell the pipeline which provider you are using.** Open
`config/api_config.yml` and find the `secrets:` section. Set
`required: true` for your chosen provider and `required: false` for all
others. For example, if you are using Anthropic:

```yaml
secrets:
  anthropic:
    required: true
  openai:
    required: false
  google:
    required: false
```

## 7. Add The Shared Access Token

The workflows need a shared token provided by the maintainer for two things:
pulling the private Docker image that runs the pipeline, and fetching updates
from the private template repository.

Add the token provided by the maintainer as a repository secret:

1. In your repository, click **Settings**.
2. In the left sidebar click **Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Enter the name and value exactly as shown below, then click **Add secret**.

```
Name:  CORE_REPO_PAT
Value: <token from maintainer>
```

If this secret is missing, workflows will fail with a clear error message.

You can override the Docker image with a repository variable if needed:

```text
JOB_HUNTER_CORE_IMAGE=ghcr.io/OWNER/REPO/job-hunter-core:tag
```

## 8. Configure Your Personal Access Token

The workflows also need a token you create yourself so they can commit results
back to your repository and run **Update From Core**.

**`GH_PAT`** — your own personal access token.

1. Go to `https://github.com/settings/personal-access-tokens/new`
   (GitHub → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token).
2. Give it a name like `job-hunt-actions`.
3. Under **Repository access**, choose **Only select repositories** and pick
   your job-hunt repository.
4. Under **Permissions → Repository permissions**, set:
   - **Contents**: Read and write
   - **Workflows**: Read and write (required for **Update From Core**)
5. Click **Generate token** and copy it immediately — GitHub only shows it once.
6. Add it as a repository secret named `GH_PAT` (same steps as above).

If this token is missing, workflows will fail with a clear error message telling
you to add it.

## 9. Optional Local Smoke Test

After package access is configured, you can test the config locally with Docker.

PowerShell:

```powershell
docker login ghcr.io
docker run --rm `
  -e JOB_HUNTER_ROOT=/workspace `
  -v "${PWD}:/workspace" `
  -w /workspace `
  ghcr.io/job-network-projects/job-hunter-core:latest `
  job-hunter config check
```

Bash:

```bash
docker login ghcr.io
docker run --rm \
  -e JOB_HUNTER_ROOT=/workspace \
  -v "$PWD:/workspace" \
  -w /workspace \
  ghcr.io/job-network-projects/job-hunter-core:latest \
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

Open the **Actions** tab in your repository (top menu bar). If you see a yellow
banner asking you to enable workflows, click **I understand my workflows, go
ahead and enable them**.

Common workflows:

- **Job Hunt Pipeline** searches configured regions and generates job artifacts.
- **Tailor Links** tailors your resume and cover letter for one or more job URLs.
- **Tailor Raw JD** tailors from a pasted job description.
- **LinkedIn Content** creates private draft ideas and engagement suggestions.
- **Update From Core** imports maintained core changes.

Scheduled weekday hunts run the primary enabled region. Secondary enabled
regions run on their configured weekday slots. Empty slots exit before expensive
pipeline work.

## 12. Pull Future Core Updates

Run **Actions -> Update From Core** in your personal repo. After it finishes,
run locally:

```bash
git pull origin main
```

Core updates preserve personal files such as your resume, story bank,
generated jobs, and config values unless a migration explicitly says otherwise.

## Troubleshooting

If a workflow cannot pull the core image, confirm package access or add
`CORE_IMAGE_PAT`.

If a workflow says an LLM provider key is missing, confirm both the GitHub secret
and the matching `config/api_config.yml` provider setting.

If generated PDFs are missing, check the workflow logs and uploaded `job_hunt.log`
artifact first. The core image already includes LaTeX and Playwright.
