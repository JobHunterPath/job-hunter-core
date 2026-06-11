"""Command-line entry point for the installed job-hunter core package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _run_pipeline(argv: list[str]) -> int:
    from job_hunter_core.pipeline.orchestrator import _build_parser, run

    return run(_build_parser().parse_args(argv))


def _run_discovery(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="job-hunter discover")
    parser.add_argument("--region", default=None, help="Region key; omit for all enabled regions.")
    args = parser.parse_args(argv)

    from job_hunter_core.discovery.discoverer import run

    run(region=args.region)
    return 0


def _run_merge_tracker(_argv: list[str]) -> int:
    from job_hunter_core.pipeline.merge_tracker import main

    return main()


def _run_resolve_hunt_region(_argv: list[str]) -> int:
    from job_hunter_core.pipeline.resolve_hunt_region import main

    return main()


def _run_linkedin(argv: list[str]) -> int:
    from job_hunter_core.linkedin.common import linkedin_enabled, load_linkedin_config

    parser = argparse.ArgumentParser(prog="job-hunter linkedin")
    parser.add_argument(
        "job",
        choices=["generate-ideas", "draft-posts", "discover-networking", "all"],
        help="LinkedIn helper job to run.",
    )
    parser.add_argument("--config", help="Path to linkedin/config.yml")
    args = parser.parse_args(argv)
    config_path = Path(args.config) if args.config else None
    config = load_linkedin_config(config_path)

    if not linkedin_enabled(config):
        print("[linkedin] LinkedIn workflow disabled.")
        return 0

    if args.job in ("generate-ideas", "all"):
        from job_hunter_core.linkedin.generate_ideas import generate

        generate(config_path)
    if args.job in ("draft-posts", "all"):
        from job_hunter_core.linkedin.draft_posts import draft

        draft(config_path)
    if args.job in ("discover-networking", "all"):
        from job_hunter_core.linkedin.discover_engagement import discover

        discover(config_path)
    return 0


def _run_config(_argv: list[str]) -> int:
    from job_hunter_core.core.config_schema import check

    return check()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-hunter",
        description="Private job-hunt automation core.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hunt = subparsers.add_parser("hunt", help="Run the hunt pipeline.")
    hunt.add_argument("--region", help="Optional search_config.yml region key.")
    hunt.add_argument("--skip-score", action="store_true")
    hunt.add_argument("--skip-validate", action="store_true")
    hunt_split = hunt.add_mutually_exclusive_group()
    hunt_split.add_argument("--scrape-only", action="store_true")
    hunt_split.add_argument("--from-snapshot", metavar="PATH")
    hunt.set_defaults(func=lambda ns: _run_pipeline(_namespace_to_args(ns)))

    tailor_links = subparsers.add_parser("tailor-links", help="Tailor from job URLs.")
    tailor_links.add_argument("--links", help="Comma-separated job URLs.")
    tailor_links.add_argument("--skip-score", action="store_true")
    tailor_links.add_argument("--skip-validate", action="store_true")
    tailor_links.add_argument("--force", action="store_true")
    tailor_links.set_defaults(
        func=lambda ns: _run_pipeline(["--mode", "tailor-links", *_namespace_to_args(ns)])
    )

    tailor_raw = subparsers.add_parser("tailor-raw", help="Tailor from raw JD text.")
    tailor_raw.add_argument("--jd", required=True)
    tailor_raw.add_argument("--title")
    tailor_raw.add_argument("--company")
    tailor_raw.add_argument("--skip-score", action="store_true")
    tailor_raw.add_argument("--skip-validate", action="store_true")
    tailor_raw.add_argument("--force", action="store_true")
    tailor_raw.set_defaults(
        func=lambda ns: _run_pipeline(["--mode", "tailor-raw", *_namespace_to_args(ns)])
    )

    discover = subparsers.add_parser("discover", help="Run weekly company discovery.")
    discover.add_argument(
        "--region", default=None, help="Region key; omit for all enabled regions."
    )
    discover.set_defaults(
        func=lambda ns: _run_discovery(["--region", ns.region] if ns.region else [])
    )

    merge_tracker = subparsers.add_parser(
        "merge-tracker",
        help="Union-merge tracker files after concurrent run conflicts.",
    )
    merge_tracker.set_defaults(func=lambda ns: _run_merge_tracker([]))

    resolve_hunt_region = subparsers.add_parser(
        "resolve-hunt-region",
        help="Resolve the scheduled/manual hunt region and emit GitHub Actions outputs.",
    )
    resolve_hunt_region.set_defaults(func=lambda ns: _run_resolve_hunt_region([]))

    linkedin = subparsers.add_parser("linkedin", help="Run LinkedIn helpers.")
    linkedin.add_argument(
        "job",
        choices=["generate-ideas", "draft-posts", "discover-networking", "all"],
    )
    linkedin.add_argument("--config")
    linkedin.set_defaults(func=lambda ns: _run_linkedin(_linkedin_args(ns)))

    config = subparsers.add_parser("config", help="Check config schema.")
    config.add_argument("action", choices=["check"])
    config.set_defaults(func=lambda ns: _run_config([]))

    return parser


def _namespace_to_args(ns: argparse.Namespace) -> list[str]:
    args: list[str] = []
    values = vars(ns)
    for key, value in values.items():
        if key in {"command", "func"} or value in (None, False):
            continue
        flag = f"--{key.replace('_', '-')}"
        if value is True:
            args.append(flag)
        else:
            args.extend([flag, str(value)])
    return args


def _linkedin_args(ns: argparse.Namespace) -> list[str]:
    args = [ns.job]
    if ns.config:
        args.extend(["--config", str(ns.config)])
    return args


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
