"""
Union-merge YAML state files when a concurrent pipeline run causes a rebase conflict.

Called by daily_jobs.yml after `git rebase --abort` to combine both runs'
processed URL lists before amending the local commit and retrying the push.
"""

from __future__ import annotations

import subprocess
import sys

import yaml

_FILES = {
    "config/applied_jobs.yml": (
        "# Tracks all job URLs and titles already processed by the pipeline.\n"
        "# Automatically updated after each run.\n"
        "# Remove a URL/title manually to reprocess that job.\n\n"
    ),
    "config/discovery_cache.yml": (
        "# Broad discovery candidate URLs already seen by the pipeline.\n"
        "# This keeps SearXNG/search API/AI discovery from rediscovering the same listings.\n\n"
    ),
}


_OBSOLETE_KEYS = {"applied_titles"}


def _union(ours: dict, theirs: dict) -> dict:
    merged: dict = {}
    for k in set(list(ours) + list(theirs)):
        if k in _OBSOLETE_KEYS:
            continue
        o = ours.get(k) or []
        t = theirs.get(k) or []
        if isinstance(o, list) or isinstance(t, list):
            merged[k] = sorted(
                set(o if isinstance(o, list) else []) | set(t if isinstance(t, list) else [])
            )
        else:
            merged[k] = o or t
    return merged


def main() -> int:
    ok = True
    for path, header in _FILES.items():
        try:
            with open(path, encoding="utf-8") as f:
                ours = yaml.safe_load(f) or {}
            result = subprocess.run(
                ["git", "show", f"origin/main:{path}"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"[merge-tracker] origin/main:{path} not found, keeping ours")
                continue
            theirs = yaml.safe_load(result.stdout) or {}
            merged = _union(ours, theirs)
            with open(path, "w", encoding="utf-8") as f:
                f.write(header)
                yaml.dump(merged, f, default_flow_style=False, allow_unicode=True)
            print(f"[merge-tracker] union-merged {path}")
        except Exception as e:
            print(f"[merge-tracker] warning: {path}: {e}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
