# Setup Reference

## GitHub Secrets

| Secret | Required | Provider | What it unlocks |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | If using Anthropic | Anthropic | Claude models |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI | GPT-4o models |
| `GOOGLE_API_KEY` | If using Google | Google | Gemini models |
| `GH_PAT` | Yes | GitHub | Update-from-template workflow, push commits |
| `BRAVE_API_KEY` | — | Brave | AI web search (job discovery) |
| `TAVILY_API_KEY` | — | Tavily | AI web search |
| `EXA_API_KEY` | — | Exa | AI web search |
| `ADZUNA_APP_ID` + `ADZUNA_API_KEY` | — | Adzuna | Adzuna job board |
| `REED_API_KEY` | — | Reed | Reed.co.uk job board |
| `RAPIDAPI_KEY` | — | RapidAPI | JSearch board |

## Prompt-based Setup (for users without Claude Code / Codex CLI / Gemini CLI)

### Prompt 1 — Configure api_config.yml

```
I am setting up a job hunting automation tool. Here is my current api_config.yml:

[PASTE config/api_config.yml content here]

My LLM provider is [Anthropic / OpenAI / Google]. Please update the file to set the
correct provider and assign suitable models for each role (scoring, tailoring,
cover_letter, jd_extraction, discovery, ai_web_search, validation). Return only the
updated YAML.
```

### Prompt 2 — Configure search_config.yml

```
Here is my current search_config.yml:

[PASTE config/search_config.yml content here]

Add a search region for me with:
- Location: [your city/country]
- Target companies: [list with career page URLs if known]
- Job titles: [list]

Return only the updated YAML.
```

### Prompt 3 — Build story bank

```
Here is my story bank template:

[PASTE story_bank.md content here]

I will share my work history. For each role, write 2–4 STAR stories (Situation, Task,
Action, Result) in the Draft section with stable IDs (ROLE-NN format), and rate each
A/B/C. Use only the facts I provide — never invent metrics or outcomes.

My work history:
[describe your roles and achievements]
```

### Prompt 4 — Build base resume

```
Here is my LaTeX resume template and story bank:

[PASTE resume_single_column.tex OR resume_double_column.tex]

[PASTE story_bank.md Draft section]

Fill in the resume with my information. Keep all LaTeX formatting intact. Use only the
experiences and stories I provided. Escape LaTeX special characters: &, %, $, #, _

My name: [name]
Contact: [email, LinkedIn, location]
Education: [degree, institution, year]
```
