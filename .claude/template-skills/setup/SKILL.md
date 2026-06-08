---
name: setup
description: One-time onboarding for a fresh job-hunter-template fork — fills in configs, builds story bank, writes base resume, and provides GitHub secrets guidance.
when_to_use: User just forked job-hunter-template and wants to configure their job search from scratch.
user-invocable: true
allowed-tools: Read Edit
author: "Abdul Basit (@abdulrbasit)"
category: tool
---

# Setup

One-time onboarding for a freshly forked `job-hunter-template` repo. Run only once, on a fresh fork.

## Token Rules

- Collect inputs one section at a time. Never read full config files back to the user.
- Edit config files directly in place.
- Confirm each section with a one-line summary, then continue to the next.
- Never invent experience, outcomes, metrics, employers, or dates.

## Confirm

Warn the user that this skill overwrites placeholder values in config and context files. Continue only after they reply `proceed`.

## Steps

Execute in order, one section at a time.

### 1. LLM Provider

Read `config/api_config.yml`.

Ask: "Which LLM provider do you want to use? Anthropic / OpenAI / Google"

Based on their answer, set `llm.default_provider` and update all `llm.providers.*` and `llm.models.*` keys:

- **Anthropic** — provider: `anthropic`; most roles: `claude-sonnet-4-6`; validation, jd_extraction, ai_web_search: `claude-haiku-4-5-20251001`
- **OpenAI** — provider: `openai`; most roles: `gpt-4o`; validation, jd_extraction, ai_web_search: `gpt-4o-mini`
- **Google** — provider: `google`; all roles: `gemini-2.0-flash`

Confirm: "LLM provider set to [provider]. GitHub secret to add: [SECRET_NAME]."

See `reference.md` for the full GitHub secrets table.

### 2. Search Region

Read `config/search_config.yml`.

Ask:
- "What city/country do you want to search in?"
- "List 3–5 target companies (and their career page URLs if you know them)."
- "List 3–5 job titles you are targeting."

Update the existing `berlin` region key (or add a `primary` key if more appropriate) with the user's location, companies, and job titles. Also update `global_search.job_titles` to match.

Confirm: "Region configured: [location] with [N] companies and [N] titles."

### 3. Scoring Threshold

Read `config/scoring_config.yml`.

Ask: "What minimum fit score do you want? (65 = broad, 75 = focused, 85 = strict — default is 70)"

Set `scoring.min_fit_score` to their answer.

Confirm: "Scoring threshold set to [N]."

### 4. Story Bank

Read `story_bank.md`.

Tell the user: "Share your work history role by role — company, title, and your key achievements, challenges, or outcomes. No need to structure them — just describe what you did."

For each role the user describes:
- Write 2–4 STAR stories (Situation → Task → Action → Result) using only the facts they stated.
- Never invent metrics, dates, employers, or outcomes. If a metric is missing, use a concrete scope anchor instead (team size, launch timeline, number of markets, stakeholder count).
- Assign stable IDs in `ROLE-NN` format where ROLE is a short label (e.g. `PM`, `ENG`, `SIDE`) and NN is a two-digit number starting at `01`.
- Rate each story A / B / C: A = specific and measurable result, B = clear but vague on impact, C = needs more detail before it can be used.

Write all stories into the **Draft** section of `story_bank.md`. Do NOT write to any Final section — the user reviews and promotes drafts themselves.

Confirm: "[N] draft stories added for [role]. Review and promote to Final when ready."

### 5. Resume

Ask: "Do you want the single-column (ATS-friendly) or double-column layout?"

Read the chosen file (`resume_single_column.tex` or `resume_double_column.tex`).

If you do not yet have the user's name and contact details, ask now.

Fill in:
- Name and contact info (email, LinkedIn URL, location)
- Work experience sections using the story bank drafts just written — one bullet per STAR story, using only the stated facts
- Education (ask if not yet provided)

Keep all existing LaTeX commands, section structure, and escaping intact. Only replace placeholder content. Escape LaTeX special characters: `&`, `%`, `$`, `#`, `_`.

Confirm: "Resume updated with [N] experience entries."

### 6. GitHub Secrets Checklist

Print the checklist below based on the provider chosen in Step 1.

Always required:
- [ ] `GH_PAT` — personal access token with Contents and Workflows read/write on this repo (see SETUP.md § 8)
- [ ] `[LLM_SECRET]` — e.g. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`

Job search providers (add the ones relevant to your region):
- [ ] `BRAVE_API_KEY` — AI web search
- [ ] `TAVILY_API_KEY` — AI web search
- [ ] `EXA_API_KEY` — AI web search
- [ ] `ADZUNA_APP_ID` + `ADZUNA_API_KEY` — Adzuna job board
- [ ] `REED_API_KEY` — Reed.co.uk job board
- [ ] `RAPIDAPI_KEY` — JSearch board

Add each secret: GitHub repo → Settings → Secrets and variables → Actions → New repository secret.

Full secrets reference is in `.claude/skills/setup/reference.md`.

### 7. First Run

Tell the user:

"Push your changes first:
```
git add config/ story_bank.md resume_single_column.tex resume_double_column.tex
git commit -m 'setup: initial configuration'
git push
```

Then go to the **Actions** tab in your GitHub repository → **Job Hunt** → **Run workflow** → leave the region field blank to run all enabled regions."

## Output

Print a summary table at the end:

| Section | Status | Notes |
|---|---|---|
| LLM provider | done | [provider], [secret name] |
| Search region | done | [location], [N] companies, [N] titles |
| Scoring threshold | done | min_fit_score: [N] |
| Story bank | done | [N] draft stories |
| Resume | done | [template chosen] |
| GitHub secrets | checklist printed | — |
| First run | instructions given | — |
