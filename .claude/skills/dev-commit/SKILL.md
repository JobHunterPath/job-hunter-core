---
name: dev-commit
description: Pre-flight checks and conventional commit message format for job-hunter-core. Runs tests, checks for secrets, stages named files, and proposes a one-line message.
when_to_use: Developer context only — use when modifying repo code or skills, not during job search. Triggered when user asks to commit, stage changes, or prepare a commit message.
disable-model-invocation: true
allowed-tools: Bash Read
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Commit

Token rule: show status, stats, and failing checks only. Do not paste full diffs or full test logs unless needed to explain a blocker.

## Step 1 — Pre-flight (run in parallel, report failures)

1. **Sensitive files** — FAIL if any staged file matches `*.env`, `*.key`, `*.pem`, `*.p12`, `*secret*`, `*credential*`, `*password*`.
2. **Context files** — WARN if `CLAUDE.md`, `AGENTS.md`, or `.claude/` files are staged. Prompt: "Context files staged — intentional?"
3. **Tests** — run `python -m pytest tests/ -q --tb=short`. A failure is a WARN that must be noted, not a hard block.
4. **Lint** — run `ruff check src/ tests/`. A failure is a WARN that must be noted.

## Step 2 — Draft message

One line only, no body:
```
type(scope): short imperative description (<=72 chars)
```
Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `chore`
Scope: the module or file area changed (e.g. `sources`, `pipeline`, `config`, `cli`, `tests`, `docker`)

## Step 3 — Present and confirm

Show: pre-flight result table, the proposed message, and `git diff --name-only --cached`.
Ask for confirmation. Never run `git commit` until the user confirms.

Stage specific files by name — NEVER `git add .` or `git add -A`. Commit with:
```
git commit -m "type(scope): description"
```

**Never add `Co-Authored-By:` lines** — the commit author is the human only. Do not add AI attribution lines regardless of which agent is running this skill.

Never amend or force-push without explicit instruction. Never push unless asked.
