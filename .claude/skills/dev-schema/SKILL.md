---
name: dev-schema
description: Guide for adding, renaming, or removing config keys in job-hunter-core config/templates/*.yml and their paired JSON Schema files.
when_to_use: Developer context only — when adding, renaming, or removing config keys in any config/templates/*.yml.
user-invocable: true
allowed-tools: Bash Read Grep
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Config Schema Guidelines

Apply these when touching any file under `config/templates/` or `config/schemas/`.

For step-by-step procedures for adding, renaming, and removing keys, see `dev-schema/reference.md`.

## Validation

After any schema change, run:

```
job-hunter config check
```

against the updated template file. It must pass before the change is committed.

## Config Migration Rule

When removing a config key that users may have in their existing configs:

1. Remove from `config/templates/*.yml` (the template is the source of truth).
2. Update the matching `config/schemas/*.schema.json`.
3. Update `get_timeout()` defaults in `core/config.py` if removing a `*.timeout_seconds` key.
4. Update `USER_PRESERVED_PREFIXES` in `.github/scripts/migrate_config.py` if the removed key was under a user-preserved path.
5. After the next template sync, `migrate_config.py` will automatically prune the obsolete key from user clones via `prune_obsolete_keys()` — no hardcoded removal lists needed.

## Docs Rule

Always update `README.md` and `SETUP.template.md` config sections in the same commit as the schema change. Never ship a schema change without updating docs.

Note: job-hunter-core does not use a `system_config.yml` or schema versioning system. Do not introduce one.
