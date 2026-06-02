#!/usr/bin/env python3
"""Assemble the public template repo from job-hunter-core source files."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FILE_MAP = {
    "README.template.md": "README.md",
    "SETUP.template.md": "SETUP.md",
    ".gitignore.template": ".gitignore",
    "profile/template-files/altacv.cls": "altacv.cls",
    "profile/template-files/project_instructions.md": "project_instructions.md",
    "profile/template-files/resume_double_column.tex": "resume_double_column.tex",
    "profile/template-files/resume_single_column.tex": "resume_single_column.tex",
    "profile/template-files/story_bank.md": "story_bank.md",
    ".github/scripts/merge_upstream.py": ".github/scripts/merge_upstream.py",
    ".github/scripts/migrate_config.py": ".github/scripts/migrate_config.py",
}

DIR_MAP = {
    ".github/template-workflows": ".github/workflows",
    ".github/searxng": ".github/searxng",
    ".claude/template-skills/setup": ".claude/skills/setup",
    "config/schemas": "config/schemas",
    "profile/template-files/linkedin": "linkedin",
}

CLEAN_DIRS = [
    ".github/scripts",
]


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    for target in CLEAN_DIRS:
        target_path = destination / target
        if target_path.exists():
            shutil.rmtree(target_path)

    for source, target in FILE_MAP.items():
        copy_file(ROOT / source, destination / target)

    for source, target in DIR_MAP.items():
        copy_tree(ROOT / source, destination / target)

    config_dir = destination / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted((ROOT / "config/templates").glob("*.yml")):
        copy_file(source, config_dir / source.name)

    print(f"[build-template] assembled template files in {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
