from __future__ import annotations

import pytest

from job_hunter_core.core import cli


def test_hunt_split_flags_are_mutually_exclusive() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["hunt", "--scrape-only", "--from-snapshot", "snapshot.json"])


def test_hunt_split_flags_forward_to_pipeline(monkeypatch) -> None:
    forwarded: list[str] = []

    def fake_run_pipeline(argv: list[str]) -> int:
        forwarded.extend(argv)
        return 0

    monkeypatch.setattr(cli, "_run_pipeline", fake_run_pipeline)
    args = cli.build_parser().parse_args(["hunt", "--region", "primary", "--scrape-only"])

    assert args.func(args) == 0
    assert forwarded == ["--region", "primary", "--scrape-only"]
