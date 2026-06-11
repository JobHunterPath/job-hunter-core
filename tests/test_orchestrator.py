"""Tests for pipeline/orchestrator.py orchestration safeguards."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from job_hunter_core.pipeline import orchestrator


def _match(idx: int) -> dict:
    return {
        "score": idx,
        "matched_keywords": [],
        "gaps": [],
        "job": {
            "title": f"Product Manager {idx}",
            "company": "TestCo",
            "url": f"https://example.com/jobs/{idx}",
            "snippet": "Product role.",
        },
    }


def test_process_jobs_caps_tailoring_to_15_highest_scores():
    jobs = [_match(idx)["job"] for idx in range(20)]
    matches = [_match(idx) for idx in range(20)]
    processed_titles = []

    def fake_process(match):
        processed_titles.append(match["job"]["title"])
        return True

    with (
        patch("job_hunter_core.pipeline.orchestrator.filter_matches", return_value=matches),
        patch("job_hunter_core.pipeline.orchestrator._process_match", side_effect=fake_process),
    ):
        processed = orchestrator._process_jobs(
            jobs,
            skip_validate=True,
            skip_score=False,
            max_years=4,
            api_cfg={},
            scoring_cfg={},
        )

    assert len(processed) == orchestrator.MAX_TAILORING_PER_RUN
    assert processed_titles == [f"Product Manager {idx}" for idx in range(19, 4, -1)]


def test_make_generated_tex_self_contained_uses_local_asset_names(tmp_path):
    image = tmp_path / "Profile-2025.png"
    image.write_bytes(b"image")
    cls = tmp_path / "altacv.cls"
    cls.write_text("class", encoding="utf-8")
    tex = "\n".join(
        [
            r"\documentclass[9pt,a4paper,ragged2e,withhyper]{../../altacv}",
            r"\photoR{2.8cm}{../../Profile-2025}",
            r"\begin{document}",
            r"\end{document}",
        ]
    )

    def fake_profile_path(key, default):
        return image if key == "profile_image" else cls

    with patch("job_hunter_core.pipeline.orchestrator.profile_path", side_effect=fake_profile_path):
        portable = orchestrator._make_generated_tex_self_contained(tex)

    assert r"\documentclass[9pt,a4paper,ragged2e,withhyper]{altacv}" in portable
    assert r"\photoR{2.8cm}{Profile-2025}" in portable


def test_copy_latex_assets_places_dependencies_in_job_dir(tmp_path):
    job_dir = tmp_path / "jobs" / "example"
    job_dir.mkdir(parents=True)
    image = tmp_path / "Profile-2025.png"
    image.write_bytes(b"image")
    cls = tmp_path / "altacv.cls"
    cls.write_text("class", encoding="utf-8")

    def fake_profile_path(key, default):
        return image if key == "profile_image" else cls

    with patch("job_hunter_core.pipeline.orchestrator.profile_path", side_effect=fake_profile_path):
        orchestrator._copy_latex_assets(job_dir)

    assert (job_dir / "Profile-2025.png").read_bytes() == b"image"
    assert (job_dir / "altacv.cls").read_text(encoding="utf-8") == "class"


def test_jobs_from_links_skips_irrelevant_extracted_title():
    irrelevant = {
        "title": "Product Engineer",
        "company": "TestCo",
        "url": "https://example.com/jobs/engineer",
        "snippet": "Engineering role.",
    }

    with (
        patch(
            "job_hunter_core.pipeline.orchestrator._load_search_rules",
            return_value=(["Product Manager"], ["engineer"]),
        ),
        patch("job_hunter_core.pipeline.orchestrator.fetch_jd", return_value=irrelevant),
        patch("job_hunter_core.pipeline.orchestrator._register_company") as register,
    ):
        jobs = orchestrator._jobs_from_links("https://example.com/jobs/engineer", False, set())

    assert jobs == []
    register.assert_not_called()


def test_hunt_no_new_jobs_is_successful_empty_run():
    args = SimpleNamespace(
        mode="hunt",
        region="magdeburg",
        scrape_only=False,
        from_snapshot=None,
        skip_validate=False,
        skip_score=False,
        force=False,
    )

    with (
        patch("job_hunter_core.pipeline.orchestrator.load_api_config", return_value={}),
        patch("job_hunter_core.pipeline.orchestrator.yaml.safe_load", return_value={"scoring": {}}),
        patch("builtins.open"),
        patch("job_hunter_core.pipeline.orchestrator.run_hunt", return_value=([], set(), set())),
    ):
        code = orchestrator.run(args)

    assert code == 0


def test_internal_hunt_split_flags_are_mutually_exclusive():
    parser = orchestrator._build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--scrape-only", "--from-snapshot", "snapshot.json"])


def test_hunt_scrape_only_emits_github_action_output_lines(tmp_path, capsys):
    args = SimpleNamespace(
        mode="hunt",
        region="primary",
        scrape_only=True,
        from_snapshot=None,
        skip_validate=False,
        skip_score=False,
        force=False,
    )
    snapshot = tmp_path / "hunt_scrape_2026-06-11_primary.json"

    with (
        patch("job_hunter_core.pipeline.orchestrator.load_api_config", return_value={}),
        patch("job_hunter_core.pipeline.orchestrator.yaml.safe_load", return_value={"scoring": {}}),
        patch("builtins.open"),
        patch(
            "job_hunter_core.pipeline.orchestrator.run_hunt_scrape_only",
            return_value=(snapshot, 2),
        ),
    ):
        code = orchestrator.run(args)

    assert code == 0
    output = capsys.readouterr().out
    assert f"snapshot_path={snapshot.as_posix()}" in output
    assert "candidate_count=2" in output
    assert "has_candidates=true" in output


def test_hunt_from_snapshot_preserves_tracker_context():
    args = SimpleNamespace(
        mode="hunt",
        region=None,
        scrape_only=False,
        from_snapshot="snapshot.json",
        skip_validate=True,
        skip_score=True,
        force=False,
    )
    job = {
        "title": "Product Manager",
        "company": "Acme",
        "url": "https://example.com/new",
        "snippet": "Role.",
    }
    processed = [{"job": job, "score": 0}]
    existing_urls = {"https://example.com/old"}

    with (
        patch("job_hunter_core.pipeline.orchestrator.load_api_config", return_value={}),
        patch("job_hunter_core.pipeline.orchestrator.yaml.safe_load", return_value={"scoring": {}}),
        patch("builtins.open"),
        patch(
            "job_hunter_core.pipeline.orchestrator.load_hunt_snapshot",
            return_value=([job], existing_urls, set()),
        ),
        patch("job_hunter_core.pipeline.orchestrator._process_jobs", return_value=processed),
        patch("job_hunter_core.pipeline.orchestrator.update_readme"),
        patch("job_hunter_core.pipeline.orchestrator.mark_processed") as mark_processed,
    ):
        code = orchestrator.run(args)

    assert code == 0
    mark_processed.assert_called_once_with([job], existing_urls, set())


def test_update_readme_includes_location_and_migrates_existing_rows(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "<!-- JOBS_TABLE_START -->",
                "| Date | Job | Score | Files |",
                "|---|---|---|---|",
                "| 2026-05-01 | [Old PM @ OldCo](https://example.com/old) | 72 | [Files](jobs/old/) |",
                "<!-- JOBS_TABLE_END -->",
            ]
        ),
        encoding="utf-8",
    )
    match = {
        "score": 88,
        "job": {
            "title": "Product | Manager",
            "company": "TestCo",
            "location": "Dublin, Ireland",
            "url": "https://example.com/jobs/pm",
        },
    }

    with (
        patch("job_hunter_core.pipeline.orchestrator.ROOT", str(tmp_path)),
        patch("job_hunter_core.pipeline.orchestrator.TODAY", "2026-05-19"),
    ):
        orchestrator.update_readme([match])

    content = readme.read_text(encoding="utf-8")
    assert "| Date | Job | Location | Score | Files |" in content
    assert "**Application stats:** 2 jobs tracked since 2026-05-01 (3 weeks)." in content
    assert (
        "| 2026-05-19 | [Product \\| Manager @ TestCo](https://example.com/jobs/pm) | Dublin, Ireland | 88 |"
        in content
    )
    assert "| 2026-05-01 | [Old PM @ OldCo](https://example.com/old) | Unknown | 72 |" in content


def test_update_readme_refreshes_existing_stats_block(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "## Applied Jobs",
                "<!-- JOBS_STATS_START -->",
                "**Application stats:** stale",
                "<!-- JOBS_STATS_END -->",
                "",
                "<!-- JOBS_TABLE_START -->",
                "| Date | Job | Location | Score | Files |",
                "|---|---|---|---|---|",
                "| 2026-05-05 | [PM @ OldCo](https://example.com/old) | Unknown | 72 | [Files](jobs/old/) |",
                "<!-- JOBS_TABLE_END -->",
            ]
        ),
        encoding="utf-8",
    )

    with (
        patch("job_hunter_core.pipeline.orchestrator.ROOT", str(tmp_path)),
        patch("job_hunter_core.pipeline.orchestrator.TODAY", "2026-05-25"),
    ):
        orchestrator.update_readme([])

    content = readme.read_text(encoding="utf-8")
    assert "**Application stats:** stale" not in content
    assert "**Application stats:** 1 job tracked since 2026-05-05 (3 weeks)." in content


def test_enrich_snippets_skips_configured_throttled_urls():
    jobs = [
        {
            "title": "Product Owner",
            "company": "LinkedCo",
            "url": "https://ca.linkedin.com/jobs/view/product-owner-123",
            "snippet": "short",
            "source": "AI web search: linkedin",
        },
        {
            "title": "Product Manager",
            "company": "ExampleCo",
            "url": "https://example.com/jobs/pm",
            "snippet": "short",
            "source": "Brave",
        },
    ]
    api_cfg = {
        "http": {
            "jd_enrichment": {
                "max_workers": 1,
                "skip_url_patterns": [r"linkedin\.com/jobs/"],
            }
        }
    }

    with patch(
        "job_hunter_core.pipeline.orchestrator.fetch_jd",
        return_value={"snippet": "rich description"},
    ) as fetch:
        enriched = orchestrator._enrich_snippets(jobs, api_cfg)

    fetch.assert_called_once_with("https://example.com/jobs/pm", use_llm=False)
    assert enriched[0]["snippet"] == "short"
    assert enriched[1]["snippet"] == "rich description"


def test_enrich_snippets_keeps_original_when_fetch_raises():
    jobs = [
        {
            "title": "Product Manager",
            "company": "ExampleCo",
            "url": "https://example.com/jobs/pm",
            "snippet": "short",
            "source": "Brave",
        },
        {
            "title": "Senior Product Manager",
            "company": "OtherCo",
            "url": "https://other.example/jobs/spm",
            "snippet": "short",
            "source": "Brave",
        },
    ]
    api_cfg = {"http": {"jd_enrichment": {"max_workers": 1, "skip_url_patterns": []}}}

    def fetch(url, use_llm=False):
        if "example.com/jobs/pm" in url:
            raise RuntimeError("temporary fetch failure")
        return {"snippet": "rich description"}

    with patch("job_hunter_core.pipeline.orchestrator.fetch_jd", side_effect=fetch):
        enriched = orchestrator._enrich_snippets(jobs, api_cfg)

    assert enriched[0]["snippet"] == "short"
    assert enriched[1]["snippet"] == "rich description"
    assert [job["url"] for job in enriched] == [job["url"] for job in jobs]


def test_drop_dead_urls_before_enrichment_uses_injected_checker_in_order():
    jobs = [
        {"title": "PM 1", "company": "A", "url": "https://example.com/1"},
        {"title": "PM 2", "company": "B", "url": "https://example.com/dead"},
        {"title": "PM 3", "company": "C", "url": "https://example.com/3"},
    ]
    calls = []
    api_cfg = {
        "llm": {"max_workers": 2},
        "http": {"url_verification": {"enabled": True, "timeout_seconds": 5, "max_workers": 2}},
    }

    def checker(url: str, timeout: int) -> bool:
        calls.append((url, timeout))
        return "dead" not in url

    alive = orchestrator.drop_dead_urls_before_enrichment(
        jobs,
        api_cfg,
        url_checker=checker,
    )

    assert [job["url"] for job in alive] == [
        "https://example.com/1",
        "https://example.com/3",
    ]
    assert sorted(calls) == [
        ("https://example.com/1", 5),
        ("https://example.com/3", 5),
        ("https://example.com/dead", 5),
    ]
