## Setup options

Choose your setup path:

### Option A — AI-assisted (recommended)

Open this repo in your AI coding assistant and run `/setup`. The assistant walks through everything and writes all config files, story bank, and base resume.

- **Claude Code**: open the repo folder, type `/setup`
- **OpenAI Codex CLI**: run `codex` in the repo folder, type `/setup`
- **Gemini CLI**: run `gemini` in the repo folder, type `/setup`

### Option B — Prompt-based (any LLM chat)

Use copy-paste prompts with ChatGPT, Claude.ai, or any LLM chat interface. Prompts are in `.claude/skills/setup/reference.md`.

### Option C — Manual

Follow the steps below.

---

# Setup Guide

This repository is your personal job-hunt workspace. It stores your resume,
story bank, config files, workflow files, and generated outputs. The automation code runs from a maintained public core image, so this
template does not need to carry Python scripts, tests, package files, or a
Dockerfile.

## 1. Install The Required Apps

Install:

- Git from `https://git-scm.com/downloads`
- Visual Studio Code from `https://code.visualstudio.com/`
- Docker Desktop from `https://www.docker.com/products/docker-desktop/`

Open Docker Desktop once and wait until the Docker engine is running.

## 2. Create Your Private Repository

1. Open the shared template repository on GitHub using the link provided by the
   maintainer.
2. Click **Use this template** (green button, top right).
3. Choose **Create a new repository**.
4. Set visibility to **Private**.
5. Give it any name you like (e.g. `my-job-hunt`).
6. Click **Create repository**.

Keep the repository private — it will contain your resume, story bank,
generated job artifacts, and API configuration.

Before running template updates, set pull request merge behavior:

1. Open **Settings → General** in your new repository.
2. Under **Pull Requests**, turn off **Allow merge commits**.
3. Keep **Allow squash merging** turned on.

## 3. Clone Your Repository

In VS Code, use **Source Control → Clone Repository**, or run:

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

## 4. Build Your Story Bank

The story bank is the most important personal file. The AI draws directly from
it when writing cover letters and tailoring resume bullets. Nothing is invented
— if a story or metric is not in the story bank, it will not appear in your
applications.

**What a story looks like**

Each entry describes one achievement or project from your work history. You do
not need polished prose — rough notes work, and the AI will structure them.

A complete story has:
- **Situation** — the context or problem you faced
- **Task** — what you were responsible for
- **Action** — what you specifically did
- **Result** — what changed, ideally with a number or concrete outcome
- **Tags** — keywords used to match this story to relevant job descriptions

**What makes a good story:**
- At least one number or concrete outcome (`reduced churn by 12%`, `launched in
  3 countries`, `cut review time from 2 weeks to 3 days`)
- A clear action you personally took, not just what the team did
- Tags that match the roles you are applying for

**What to collect before you start:**
- Your LinkedIn profile or existing CV
- Performance reviews or self-assessments
- Any emails, slide decks, or documents that mention specific results
- Notes about projects you are proud of

**AI prompt — use inside VS Code with Claude Code, Copilot, or Codex**

The AI helper can see `story_bank.md` in your open repo and preserve its
format. Open a chat in VS Code and paste this:

```text
Help me build my story bank in story_bank.md.

Files to edit:
- story_bank.md

Do not edit:
- resume .tex files
- config files
- src/
- tests/
- .github/workflows/

Task:
- Add my raw notes as draft entries first.
- Convert notes to final STAR stories only when there is enough detail.
- Assign a new story ID for each new entry (continue from the last existing ID).
- Preserve all existing stories and their IDs exactly.

Hard rules:
- Do not invent metrics, employers, titles, skills, dates, or outcomes.
- If no metric is verified, use a concrete scope anchor instead (team size,
  number of markets, system scale).
- If a story is too thin for a final entry, keep it as a draft and note what
  is missing.
- Preserve the existing markdown headings and table formats.
- Do not suggest changes to scripts, tests, workflows, or code files.

My notes:
[PASTE YOUR CV, LINKEDIN SUMMARY, ACHIEVEMENTS, OR ROUGH NOTES]
```

**AI prompt — browser chatbot fallback**

Use this if you prefer to work in a separate AI chat rather than VS Code:

```text
I have a story bank and I want to add stories from my background.

Hard rules:
- Do not invent metrics, employers, titles, skills, dates, or outcomes.
- Use only the notes I provide.
- Keep all existing stories and their IDs unchanged.
- Preserve the markdown headings and table formats exactly.
- Return the complete updated file.

Current story bank:
[PASTE FULL STORY_BANK.MD CONTENTS]

My notes:
[PASTE YOUR CV, LINKEDIN SUMMARY, ACHIEVEMENTS, OR ROUGH NOTES]
```

Review every final story before pushing. If a claim is not interview-safe,
move it back to draft.

## 5. Update Your Resume

The repo includes two LaTeX resume layouts: `resume_double_column.tex` and
`resume_single_column.tex`. Choose one and fill it in. The pipeline creates a
tailored copy for each job without changing your original.

**AI prompt — VS Code:**

```text
Update my LaTeX resume without changing the template structure.

Files to read:
- the resume .tex file I am editing
- story_bank.md (for context on metrics and achievements)

Do not edit:
- config files
- src/
- tests/
- .github/workflows/

Rules:
- Preserve existing LaTeX commands, escaping, sections, and layout.
- Use only factual content from my notes.
- Do not invent metrics, employers, titles, dates, skills, or outcomes.
- If a detail is missing, leave a TODO comment instead of guessing.
- Do not change config files or automation code.

My resume notes:
[PASTE YOUR CURRENT CV TEXT OR BULLET POINTS]
```

**Browser chatbot fallback:**

```text
Update this LaTeX resume using only the notes I provide.

Rules:
- Preserve the LaTeX template structure exactly.
- Escape LaTeX special characters: &, %, $, #, _
- Do not invent metrics, employers, titles, skills, dates, or outcomes.
- Return only the complete updated .tex file.

LaTeX resume:
[PASTE FULL .TEX FILE]

My notes:
[PASTE YOUR CURRENT CV OR RESUME BULLETS]
```

After editing the resume, open `config/api_config.yml` and set the file name:

```yaml
profile:
  resume_tex: "resume_double_column.tex"   # or resume_single_column.tex
  story_bank: "story_bank.md"
```

**Editing LaTeX in VS Code with live preview**

Install the **LaTeX Workshop** extension (publisher: James Yu, ID: `james-yu.latex-workshop`) from the VS Code Extensions panel. Then create `.vscode/settings.json` in your repo root with:

```json
{
  "latex-workshop.latex.recipe.default": "pdflatex",
  "latex-workshop.latex.tools": [
    {
      "name": "pdflatex",
      "command": "pdflatex",
      "args": ["-synctex=1", "-interaction=nonstopmode", "-file-line-error", "%DOC%"]
    }
  ],
  "latex-workshop.latex.recipes": [
    { "name": "pdflatex", "tools": ["pdflatex"] }
  ],
  "latex-workshop.view.pdf.viewer": "tab",
  "latex-workshop.latex.autoBuild.run": "onSave"
}
```

You also need a local LaTeX distribution for VS Code to build PDFs: **MiKTeX** on Windows (`https://miktex.org/download`), **MacTeX** on macOS (`https://tug.org/mactex/`), or `sudo apt install texlive-full` on Linux. The pipeline itself compiles PDFs inside Docker, so a local distribution is only needed for the live-preview workflow.

Press `Ctrl+Alt+V` (`Cmd+Alt+V` on Mac) to open the PDF preview panel. The file rebuilds automatically on every save.

> **Single-column photo:** place your image file (e.g. `photo.jpg`) in the same folder as the `.tex` file, then follow the commented-out instructions in the `%----------HEADING----------` block.

## 6. Configure Your Search

Open the config files and fill in the details for your situation.

**`config/search_config.yml`** — companies and job titles:

Set the job titles you want to search for, the region where you want to work,
and a list of company career pages to check every day. The default region is
`primary`; change its `location` to your target city or country.

Use this AI prompt to seed your company list:

```text
Find 30 companies whose career pages a job-hunt bot should check daily.

Region: [CITY OR COUNTRY]
Target roles: [YOUR JOB TITLES]
Preferences: [INDUSTRY, COMPANY SIZE, REMOTE/HYBRID/ONSITE]
Avoid: [ANY COMPANIES OR INDUSTRIES TO EXCLUDE]

Return YAML only, formatted like this:
companies:
  - name: Company Name
    career_url: careers.company.com

Rules:
- Use the career subdomain or ATS board domain, not a specific job listing URL.
- Do not include duplicate companies.
- Do not change any other files.
```

Paste the returned YAML under the `companies:` key in your `primary` region.

**Weekly company discovery** - the company_discovery workflow runs weekly and
uses two sources. ATS/search discovery looks for real postings from your
configured regions and job titles. LLM discovery suggests companies from the
simple sector names in `discovery.sectors`. Add or remove sector strings to
match the industries you want to target. The `{location}` placeholder is filled
in from each region's `location` value.

Industries listed in `exclusion_rules.excluded_industries` are passed to the LLM
as off-limits during discovery and are also used by the scraper's job filter to
skip postings from those industries.

**`config/scoring_config.yml`** — fit threshold:

- `min_fit_score`: jobs scoring below this are skipped (default `70` out of 100).
- `max_years_experience_required`: jobs requiring more years than this are
  skipped.

**`config/cover_letter_config.yml`** — your background:

Update `candidate_background` with a short paragraph about your current role
and what you bring to a new position. Keep it current — this is what the AI
opens every cover letter with.

## 7. Configure API Keys

The pipeline needs at least one LLM provider key to score jobs and write cover
letters.

**Get an API key** from one of these providers:

| Provider | Sign-up page | GitHub Secret name |
|---|---|---|
| Anthropic (recommended) | `https://console.anthropic.com` → API Keys | `ANTHROPIC_API_KEY` |
| OpenAI | `https://platform.openai.com/api-keys` | `OPENAI_API_KEY` |
| Google | `https://aistudio.google.com/apikey` | `GOOGLE_API_KEY` |

Job-search providers — add the ones relevant to your region and search strategy:

| Provider | GitHub Secret name |
|---|---|
| Brave Search | `BRAVE_API_KEY` |
| Tavily | `TAVILY_API_KEY` |
| Exa | `EXA_API_KEY` |
| RapidAPI / JSearch | `RAPIDAPI_KEY` |
| Adzuna (Canada, UK, DE, NL, SG, AU…) | `ADZUNA_APP_ID` + `ADZUNA_API_KEY` |
| Reed.co.uk (UK / Ireland) | `REED_API_KEY` |

The pipeline skips each source silently if its key is absent.

- **Adzuna**: Register free at https://developer.adzuna.com/ — both `ADZUNA_APP_ID` and `ADZUNA_API_KEY` appear on your application dashboard.
- **Reed**: Register free at https://www.reed.co.uk/developers/jobseeker — the key is shown on your profile page.

**Add each key as a GitHub secret:**

1. In your repository, click **Settings** (top menu).
2. In the left sidebar click **Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Enter the secret name (e.g. `ANTHROPIC_API_KEY`) and paste your key.
5. Click **Add secret**.

**Tell the pipeline which provider you are using.** Open
`config/api_config.yml`, find the `secrets:` section, and set `required: true`
for your provider:

```yaml
secrets:
  anthropic:
    required: true
  openai:
    required: false
  google:
    required: false
```

## 8. Configure Your Personal Access Token

The workflows need a token you create yourself so they can commit results back
to your repository, open template update pull requests, and update maintained
workflow files when the template changes.

1. Go to `https://github.com/settings/personal-access-tokens/new`
2. Name it `job-hunt-actions`.
3. Under **Repository access**, choose **Only select repositories** and pick
   your job-hunt repository.
4. Under **Permissions → Repository permissions**, set:
   - **Contents**: Read and write
   - **Workflows**: Read and write
5. Click **Generate token** and copy it immediately — GitHub only shows it once.
6. Add it as a repository secret named `GH_PAT`.

## 9. Optional: Test Locally

This step is entirely optional — GitHub Actions handles everything without a
local run. Skip to **Step 11** if you prefer.

### Store Keys In The OS Keychain First

Never paste API keys or access tokens directly into a terminal command. Use
Python keyring to store them in your operating system's secure credential store
(Windows Credential Manager, macOS Keychain, or Linux Secret Service). Keys
stored this way are encrypted at rest and only your user account can read them.

Install keyring (one time):

```bash
pip install keyring
```

Store each API key you need locally. The commands below prompt you to type or paste
the value — the input is hidden and the key is never written to your command
history:

**PowerShell:**

```powershell
python -c "import keyring, getpass; keyring.set_password('job-hunter', 'ANTHROPIC_API_KEY', getpass.getpass('ANTHROPIC_API_KEY: '))"
```

**Bash (macOS / Linux):**

```bash
python3 -c "import keyring, getpass; keyring.set_password('job-hunter', 'ANTHROPIC_API_KEY', getpass.getpass('ANTHROPIC_API_KEY: '))"
```

Replace `ANTHROPIC_API_KEY` with `OPENAI_API_KEY` or `GOOGLE_API_KEY` if
you are using a different provider.

### Run The Config Check

**PowerShell:**

```powershell
$env:LLM_KEY = python -c "import keyring; print(keyring.get_password('job-hunter', 'ANTHROPIC_API_KEY'))"
docker run --rm `
  -e ANTHROPIC_API_KEY=$env:LLM_KEY `
  -e JOB_HUNTER_ROOT=/workspace `
  -v "${PWD}:/workspace" `
  -w /workspace `
  ghcr.io/jobhunterpath/job-hunter-core:latest `
  job-hunter config check
```

**Bash:**

```bash
LLM_KEY=$(python3 -c "import keyring; print(keyring.get_password('job-hunter', 'ANTHROPIC_API_KEY'))")
docker run --rm \
  -e ANTHROPIC_API_KEY="$LLM_KEY" \
  -e JOB_HUNTER_ROOT=/workspace \
  -v "$PWD:/workspace" \
  -w /workspace \
  ghcr.io/jobhunterpath/job-hunter-core:latest \
  job-hunter config check
```

Replace `ANTHROPIC_API_KEY` with your provider's environment variable name if
you are using OpenAI or Google.

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

Open the **Actions** tab in your repository. If you see a yellow banner asking
you to enable workflows, click **I understand my workflows, go ahead and enable
them**.

Available workflows:

- **Job Hunt** — searches configured regions and generates tailored resume and
  cover letter files. By default it runs once per weekday for your primary
  region on the schedule in `job_hunt.yml`.
- **Company Discovery** — discovers new company career pages and prepares them
  for review. Run manually when you want fresh leads.
- **Tailor From Links** — tailors your resume and cover letter for specific job
  URLs you paste in. No search is run.
- **Tailor From Raw Job Description** — tailors from a pasted job description
  and title, without a URL.
- **Update From Template** — imports the latest maintained config, workflow,
  and documentation changes from the template.

Run **Job Hunt** manually once to confirm everything is working. Generated
files appear in:

```text
jobs/YYYY-MM-DD_company_role/
```

Always review the tailored resume and cover letter before submitting an
application.

## 12. Pull Future Template Updates

When the maintainer announces an update:

1. Run **Actions → Update From Template** in your repository. It opens a pull
   request with the incoming changes.
2. Review and squash-merge the pull request on GitHub.
3. Pull the merged changes to your local machine:

```bash
git pull origin main
```

Template updates preserve your personal files — resume, story bank, project
instructions, generated jobs, and existing config values — unless a migration
note says otherwise.

## 13. Advanced Features

These are all disabled by default. Enable them once the basic pipeline is
running and you are satisfied with the results.

### More Regions

The default setup has one `primary` region. To search in a second city or
country:

1. Open `config/search_config.yml` and add a second region block:

```yaml
regions:
  primary:
    enabled: true
    location: "Berlin, Germany"
    companies:
      - name: Example Company
        career_url: careers.example.com
  secondary:
    enabled: true
    location: "Amsterdam, Netherlands"
    companies:
      - name: Another Company
        career_url: careers.another.com
```

2. Open `.github/workflows/job_hunt.yml` and add a second cron line — one per
   enabled region — plus a matching line in `HUNT_SCHEDULES`. Follow the
   existing comment in that file.

### AI Web Search

AI web search uses your LLM provider to search Greenhouse, Lever, Ashby, and
other job boards by title and region. It costs LLM credits on top of normal
scoring and tailoring usage.

Open `config/api_config.yml` and set:

```yaml
http:
  search_providers:
    ai_web_search:
      enabled: true
```

### LinkedIn Content

The LinkedIn workflow is disabled by default. To enable it:

1. Open `linkedin/config.yml` and set `linkedin.enabled: true`. Fill in your
   `positioning`, `audience`, and `content_pillars`.
2. Rename `.github/workflows/linkedin_content.yml.disabled` to
   `linkedin_content.yml`.
3. Open that file, uncomment the `schedule:` block, and adjust the cron times
   to your preferred schedule — or leave it and trigger manually instead.
4. Commit and push.

The workflow derives role-specific LinkedIn search topics from your positioning,
internal defaults, and `config/search_config.yml`, dedupes with
`linkedin/state.yml`, writes review queues under `linkedin/`, and never posts,
comments, follows, connects, messages, or likes automatically.

Run **Actions → LinkedIn Content** manually and choose what to generate.
Review everything in `linkedin/` before using it.

### Google Free Tier

Google Gemini has a free API tier. To use it:

1. In `config/api_config.yml`, set `llm.default_provider: google` and update
   `llm.models.*` to Gemini model names.
2. Set `llm.max_workers: 2` to stay within the free-tier rate limit.
3. Add `GOOGLE_API_KEY` as a GitHub secret and set `secrets.google.required: true`.

Find Gemini model names at `https://ai.google.dev/gemini-api/docs/models`.

## Troubleshooting

**Workflow fails with an image pull error**

Confirm the public core image is available: `ghcr.io/jobhunterpath/job-hunter-core:latest`.
If you override `JOB_HUNTER_CORE_IMAGE`, confirm that image name and tag exist.

**Workflow fails with "GitHub Actions is not permitted to create or approve pull requests"**

Go to your repository → **Settings** → **Actions** → **General** → scroll to
**Workflow permissions** → enable **"Allow GitHub Actions to create and approve
pull requests"** → Save.

**Update From Template cannot push workflow files**

Confirm `GH_PAT` is added as a GitHub secret and has **Contents: Read and write**
and **Workflows: Read and write** on this repository.

**Workflow says an LLM provider key is missing**

Confirm both the GitHub secret (e.g. `ANTHROPIC_API_KEY`) and the matching
`config/api_config.yml` `secrets.<provider>.required: true` setting are in
place.

**Generated PDFs are missing**

Check the workflow logs and the uploaded `job_hunt.log` artifact. The core
image includes LaTeX — errors in your `.tex` file (unescaped `&`, `%`, `$`,
`#`, `_`, or a missing brace) are the most common cause.

**No jobs found after the first run**

Check `config/search_config.yml`. Confirm the `primary` region has
`enabled: true`, at least one company is listed under `companies:`, and
`global_search.job_titles` contains the titles you want.

**Push fails**

Sign in to GitHub through VS Code or use a personal access token when prompted
for a password.
