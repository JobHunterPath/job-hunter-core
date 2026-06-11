# Dev-Code Reference

## Docker-First Deployment Guidelines

- The deployment target is Docker; do not add system-level dependencies that are not installable via `pip` or already present in the base image.
- Do not read from `~/.config`, `~/.local`, or other user-home paths that will not exist inside a container. Read all config from paths relative to the project root or from environment variables.
- Environment variables are the canonical way to pass secrets and runtime overrides into the container. Never hard-code credentials or paths that differ between environments.
- If a new external tool or binary is required, note the Dockerfile change needed alongside the code change.

## Testing Guidelines

- Add or update tests for new public behavior and changed config keys.
- Mock network, browser, subprocess, and external service calls at the point of use.
- Keep fixtures small, deterministic, and local to the test unless reuse is valuable.
- Prefer testing observable behavior over private implementation details.
- Run `python -m pytest tests/ -q --tb=short` before committing code changes.
- Run `ruff check src/ tests/` to catch lint issues before committing.
