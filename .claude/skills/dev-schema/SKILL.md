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

## Adding a Key (backward-compatible)

1. Add the key to the relevant `config/templates/<name>.yml` with a sensible default value.
2. Add the key to the matching `config/schemas/<name>.schema.json`: declare its type, add it to `properties`, and add it to `required` only if there is no safe default.
3. Update the config reference section in both `README.md` and `SETUP.template.md` to document the new key, its type, its default, and what it controls.
4. Run `job-hunter config check` against the updated template to confirm it passes validation before committing.

## Renaming a Key (breaking)

A rename is a removal plus an addition. Treat it as both:

- Complete the removal steps for the old key name.
- Complete the addition steps for the new key name.
- Note the rename prominently in the PR description so reviewers understand the breaking nature.
- Announce the rename in the release notes with the old name, the new name, and the migration action (find-replace in user config files).

Do not silently rename a key and ship it without documentation. Users with existing config files will break on upgrade.

## Removing a Key (breaking)

1. Remove the key from the YAML template.
2. Remove the key from the JSON schema: delete it from `properties` and from `required` if it was listed there.
3. Grep for the key name in `src/` to find every place the code reads it. Remove or replace all those reads.
4. Update `README.md` and `SETUP.template.md` to remove all references to the deleted key.
5. Announce the removal in the release notes with a migration note for users who have the key in their config.

Grep command to find source references before removing:

```
grep -r "<key_name>" src/
```

## Schema File Format

- Use JSON Schema draft-07.
- Set `"additionalProperties": false` on every object schema to catch typos in user config files early.
- List all required fields explicitly in `"required"`. Do not rely on default inference to make a field implicitly required.
- Keep descriptions on every property: a one-line plain-English explanation of what the key controls.

Example property entry:

```json
"max_results": {
  "type": "integer",
  "description": "Maximum number of job listings to return per search run.",
  "default": 50
}
```

## Validation

After any schema change, run:

```
job-hunter config check
```

against the updated template file. It must pass before the change is committed. A schema change that fails its own template is not ready to ship.

## Docs Rule

Always update `README.md` and `SETUP.template.md` config sections in the same commit as the schema change. Never ship a schema change without updating docs. Reviewers should be able to confirm doc and schema are in sync by reading the diff.

Note: job-hunter-core does not use a `system_config.yml` or schema versioning system. Do not introduce one.
