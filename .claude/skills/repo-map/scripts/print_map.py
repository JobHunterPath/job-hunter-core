#!/usr/bin/env python3
"""Print a compact LOC map of src/job_hunter_core/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "src" / "job_hunter_core"
lines: list[tuple[str, int]] = []
for p in sorted(ROOT.rglob("*.py")):
    rel = p.relative_to(ROOT)
    loc = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
    lines.append((str(rel), loc))

print(f"{'Module':<60} {'LOC':>6}")
print("-" * 67)
for rel, loc in lines[:50]:
    print(f"{rel:<60} {loc:>6}")
if len(lines) > 50:
    print(f"... ({len(lines) - 50} more modules)")
print(f"\nTotal: {len(lines)} modules, {sum(l for _, l in lines)} non-empty lines")
