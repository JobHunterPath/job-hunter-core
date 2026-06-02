#!/usr/bin/env python3
"""Preserve marked private sections while accepting upstream file structure."""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER_RE = re.compile(r"(<!-- (\w+)_START -->)(.*?)(<!-- \2_END -->)", re.DOTALL)


def extract_sections(text: str) -> dict[str, str]:
    return {match.group(2): match.group(3) for match in MARKER_RE.finditer(text)}


def inject_sections(upstream: str, private_sections: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(2)
        return match.group(1) + private_sections.get(name, match.group(3)) + match.group(4)

    return MARKER_RE.sub(replace, upstream)


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} <upstream_file> <private_file> <output_file>",
            file=sys.stderr,
        )
        return 1

    upstream_path, private_path, output_path = map(Path, sys.argv[1:])
    upstream = upstream_path.read_text(encoding="utf-8")

    try:
        private_sections = extract_sections(private_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        private_sections = {}

    output_path.write_text(inject_sections(upstream, private_sections), encoding="utf-8")
    print(
        f"[merge-upstream] merged {upstream_path} -> {output_path} "
        f"({len(private_sections)} private section(s) preserved)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
