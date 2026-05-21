"""Repository config schema checks and small migrations."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from core.config import ROOT

CURRENT_SCHEMA_VERSION = 1
SYSTEM_CONFIG = ROOT / "config" / "system_config.yml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def configured_schema_version() -> int:
    data = _read_yaml(SYSTEM_CONFIG)
    return int(data.get("schema_version") or 0)


def check() -> int:
    version = configured_schema_version()
    if version == CURRENT_SCHEMA_VERSION:
        print(f"[config] schema_version={version} ok")
        return 0
    if version == 0:
        print(
            f"::warning::config/system_config.yml is missing; "
            f"run `job-hunter config migrate` to create schema_version={CURRENT_SCHEMA_VERSION}."
        )
        return 0
    if version < CURRENT_SCHEMA_VERSION:
        print(
            f"::warning::config schema_version={version} is older than "
            f"{CURRENT_SCHEMA_VERSION}; run `job-hunter config migrate`."
        )
        return 0
    print(
        f"::error::config schema_version={version} is newer than this core "
        f"supports ({CURRENT_SCHEMA_VERSION}). Upgrade the core image."
    )
    return 1


def migrate(target_version: int = CURRENT_SCHEMA_VERSION) -> int:
    if target_version != CURRENT_SCHEMA_VERSION:
        print(f"::error::Unsupported target schema version: {target_version}")
        return 1

    data = _read_yaml(SYSTEM_CONFIG)
    current = int(data.get("schema_version") or 0)
    if current > CURRENT_SCHEMA_VERSION:
        print(
            f"::error::config schema_version={current} is newer than this core "
            f"supports ({CURRENT_SCHEMA_VERSION})."
        )
        return 1

    data.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    _write_yaml(SYSTEM_CONFIG, data)
    print(f"[config] migrated schema_version {current or 'missing'} -> {CURRENT_SCHEMA_VERSION}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-hunter config")
    parser.add_argument("action", choices=["check", "migrate"])
    parser.add_argument("--target-version", type=int, default=CURRENT_SCHEMA_VERSION)
    args = parser.parse_args(argv)

    if args.action == "check":
        return check()
    return migrate(args.target_version)


if __name__ == "__main__":
    raise SystemExit(main())
