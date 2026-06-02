#!/usr/bin/env python3
"""Deep-merge upstream config defaults into a user config file."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

USER_NAMESPACE_PATHS = frozenset(
    {
        "search_config.yml.regions",
    }
)


def deep_merge(upstream: dict, user: dict, prefix: str = "") -> tuple[dict, list[str]]:
    result = dict(user)
    added: list[str] = []

    for key, upstream_value in upstream.items():
        key_path = f"{prefix}.{key}" if prefix else str(key)
        if key not in user:
            if prefix not in USER_NAMESPACE_PATHS:
                result[key] = upstream_value
                added.append(key_path)
        elif isinstance(upstream_value, dict) and isinstance(user[key], dict):
            result[key], child_added = deep_merge(upstream_value, user[key], key_path)
            added.extend(child_added)

    return result, added


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} <upstream_file> <user_file> <output_file>",
            file=sys.stderr,
        )
        return 1

    upstream_path, user_path, output_path = map(Path, sys.argv[1:])
    upstream = yaml.safe_load(upstream_path.read_text(encoding="utf-8")) or {}

    try:
        user = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        user = {}
    except yaml.YAMLError as exc:
        print(f"::warning::Could not parse {user_path}: {exc}")
        return 0

    merged, added = deep_merge(upstream, user, upstream_path.name)
    output_path.write_text(
        yaml.safe_dump(merged, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )

    if added:
        print(f"[migrate-config] {upstream_path.name}: added {len(added)} key(s)")
    else:
        print(f"[migrate-config] {upstream_path.name}: no new keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
