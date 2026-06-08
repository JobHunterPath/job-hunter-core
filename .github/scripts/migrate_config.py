#!/usr/bin/env python3
"""Deep-merge upstream config defaults into a user config file, then prune obsolete keys.

Usage: migrate_config.py <upstream_file> <user_file> <output_file>

Merge behaviour
---------------
- Keys present in upstream but missing from user are added (recursive for dicts).
- Lists and scalar values: user wins; upstream value is added only when the key
  is absent from user entirely.
- User values are never overwritten.

Prune behaviour
---------------
After merging, any key in the result that is no longer present in the upstream
template is removed.  Paths listed in USER_PRESERVED_PREFIXES are excluded from
pruning because the user is expected to add their own entries there (e.g. their
own region names, custom company exclusions).

The combined effect: the result always looks like the current template shape,
while preserving every value the user has customised.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Paths under which the user adds their own keys that are not in the upstream
# template.  Pruning never touches anything under these prefixes.
# Keys are config file basenames; values are sets of dot-delimited path prefixes.
USER_PRESERVED_PREFIXES: dict[str, frozenset[str]] = {
    "api_config.yml": frozenset(
        {
            "profile",  # user-specific file paths
            "llm.providers",  # user assigns tasks to LLM providers
            "llm.models",  # user picks model names per task
            "llm.max_tokens",  # user may tune per-task token budgets
            "http.api_budgets.monthly_limits",  # user sets their own quota numbers
        }
    ),
    "search_config.yml": frozenset(
        {
            "regions",  # user adds their own region definitions
            "excluded_companies",  # user's personal exclusion list
            "exclusion_rules",  # user's custom filter rules
            "global_search.job_titles",  # user's job title list
            "discovery.sectors",  # user's sector list for LLM discovery
        }
    ),
}

# Sections the user owns entirely: once the user has any content under a key,
# upstream template keys are never injected into it.  An absent or empty section
# still receives the template seed (fresh-install behaviour is preserved).
USER_OWNED_SECTIONS: dict[str, frozenset[str]] = {
    "search_config.yml": frozenset(
        {
            "regions",  # user's region definitions are theirs alone
        }
    ),
}


def _is_preserved(path: str, preserved: frozenset[str]) -> bool:
    """Return True if *path* is at or under any preserved prefix."""
    return any(path == p or path.startswith(p + ".") for p in preserved)


def deep_merge(
    upstream: dict,
    user: dict,
    prefix: str = "",
    owned: frozenset[str] = frozenset(),
) -> tuple[dict, list[str]]:
    """Merge upstream defaults into user dict.  Returns (merged, list_of_added_paths)."""
    result = dict(user)
    added: list[str] = []

    for key, upstream_value in upstream.items():
        key_path = f"{prefix}.{key}" if prefix else str(key)
        if key not in user:
            result[key] = upstream_value
            added.append(key_path)
        elif isinstance(upstream_value, dict) and isinstance(user[key], dict):
            # User-owned sections with existing content are never overridden by
            # upstream keys — the user's sub-tree is kept as-is.  An empty section
            # still gets the template seed so fresh installs work correctly.
            if key_path in owned and user[key]:
                result[key] = user[key]
            else:
                result[key], child_added = deep_merge(upstream_value, user[key], key_path, owned)
                added.extend(child_added)

    return result, added


def prune_obsolete_keys(
    user: dict,
    template: dict,
    preserved: frozenset[str],
    path: str = "",
) -> tuple[dict, list[str]]:
    """Remove keys from *user* that are no longer present in *template*.

    Keys under *preserved* prefixes are never removed.
    Returns (pruned_dict, list_of_removed_paths).
    """
    result: dict = {}
    removed: list[str] = []

    for key, val in user.items():
        full = f"{path}.{key}" if path else key

        if _is_preserved(full, preserved):
            result[key] = val
            continue

        if key not in template:
            removed.append(full)
            continue

        if isinstance(val, dict) and isinstance(template[key], dict):
            pruned_child, child_removed = prune_obsolete_keys(val, template[key], preserved, full)
            result[key] = pruned_child
            removed.extend(child_removed)
        else:
            result[key] = val

    return result, removed


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

    preserved = USER_PRESERVED_PREFIXES.get(upstream_path.name, frozenset())
    owned = USER_OWNED_SECTIONS.get(upstream_path.name, frozenset())
    merged, added = deep_merge(upstream, user, owned=owned)
    pruned, removed = prune_obsolete_keys(merged, upstream, preserved)

    output_path.write_text(
        yaml.safe_dump(pruned, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )

    if added:
        print(
            f"[migrate-config] {upstream_path.name}: added {len(added)} key(s): {', '.join(added)}"
        )
    else:
        print(f"[migrate-config] {upstream_path.name}: no new keys")

    if removed:
        print(
            f"[migrate-config] {upstream_path.name}: pruned {len(removed)} obsolete key(s): {', '.join(removed)}"
        )
    else:
        print(f"[migrate-config] {upstream_path.name}: no obsolete keys")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
