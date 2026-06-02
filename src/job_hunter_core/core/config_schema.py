"""Config YAML validation against JSON Schema files bundled with the package."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from job_hunter_core.core.config import ROOT

# config_schema.py → core/ → job_hunter_core/ → src/ → repo root → config/schemas/
_SCHEMAS_DIR = Path(__file__).parent.parent.parent.parent / "config" / "schemas"
# Falls back to looking relative to ROOT for Docker installs
if not _SCHEMAS_DIR.exists():
    _SCHEMAS_DIR = ROOT / "config" / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    """Load a JSON Schema file by stem name (e.g. 'scoring_config')."""
    import json

    path = _SCHEMAS_DIR / f"{name}.schema.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_config(config_dict: dict[str, Any], schema_name: str) -> list[str]:
    """
    Validate config_dict against the named JSON Schema.
    Returns list of error messages (empty = valid).
    """
    try:
        import jsonschema
    except ImportError:
        return []  # jsonschema optional; skip validation if not installed

    schema = _load_schema(schema_name)
    if not schema:
        return []

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(config_dict), key=lambda e: list(e.path))
    return [f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]


def check() -> int:
    """Validate all known config YAMLs and report results."""
    config_dir = ROOT / "config"
    schemas = {
        "api_config": config_dir / "api_config.yml",
        "search_config": config_dir / "search_config.yml",
        "scoring_config": config_dir / "scoring_config.yml",
        "cover_letter_config": config_dir / "cover_letter_config.yml",
        "tailoring_config": config_dir / "tailoring_config.yml",
    }

    all_ok = True
    for schema_name, config_path in schemas.items():
        if not config_path.exists():
            print(f"[config] {config_path.name}: not found (skipped)")
            continue
        with config_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        errors = validate_config(data, schema_name)
        if errors:
            all_ok = False
            print(f"[config] {config_path.name}: INVALID")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"[config] {config_path.name}: ok")

    if all_ok:
        print("[config] all configs valid")
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-hunter config")
    parser.add_argument("action", choices=["check"])
    parser.parse_args(argv)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
