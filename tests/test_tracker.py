"""Tests for tracking/tracker.py — uses temp files, no API calls."""

from unittest.mock import patch

import yaml

from job_hunter_core.tracking import tracker


def test_load_processed_returns_empty_when_no_file(tmp_path):
    with patch.object(tracker, "TRACKER_FILE", str(tmp_path / "applied_jobs.yml")):
        urls, titles = tracker.load_processed()
    assert urls == set()
    assert titles == set()


def test_load_processed_returns_urls_from_file(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    f.write_text(yaml.dump({"processed": ["https://a.com", "https://b.com"]}))
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        urls, titles = tracker.load_processed()
    assert urls == {"https://a.com", "https://b.com"}
    assert titles == set()


def test_load_processed_handles_empty_file(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    f.write_text("")
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        urls, titles = tracker.load_processed()
    assert urls == set()
    assert titles == set()


def test_save_processed_writes_sorted_urls(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.save_processed({"https://b.com", "https://a.com"}, set())
    data = yaml.safe_load(f.read_text())
    assert data["processed"] == ["https://a.com", "https://b.com"]


def test_save_and_reload_roundtrip(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    urls = {"https://x.com/job/1", "https://y.com/job/2"}
    titles = {"testco::product manager"}
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.save_processed(urls, titles)
        reloaded_urls, reloaded_titles = tracker.load_processed()
    assert reloaded_urls == urls
    assert reloaded_titles == titles


def test_filter_new_jobs_removes_already_processed(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    f.write_text(yaml.dump({"processed": ["https://seen.com"]}))
    jobs = [
        {"title": "PM", "company": "Seen", "url": "https://seen.com"},
        {"title": "PO", "company": "New", "url": "https://new.com"},
    ]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        new_jobs, existing_urls, existing_titles = tracker.filter_new_jobs(jobs)
    assert len(new_jobs) == 1
    assert new_jobs[0]["url"] == "https://new.com"
    assert "https://seen.com" in existing_urls


def test_filter_new_jobs_all_new_when_no_tracker(tmp_path):
    with patch.object(tracker, "TRACKER_FILE", str(tmp_path / "applied_jobs.yml")):
        new_jobs, existing_urls, existing_titles = tracker.filter_new_jobs(
            [
                {"title": "PM", "company": "X", "url": "https://x.com"},
            ]
        )
    assert len(new_jobs) == 1
    assert existing_urls == set()
    assert existing_titles == set()


def test_mark_processed_merges_with_existing(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    existing_urls = {"https://old.com"}
    existing_titles = set()
    jobs = [{"title": "PM", "company": "New", "url": "https://new.com"}]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.mark_processed(jobs, existing_urls, existing_titles)
        reloaded_urls, _ = tracker.load_processed()
    assert reloaded_urls == {"https://old.com", "https://new.com"}


def test_mark_processed_deduplicates(tmp_path):
    f = tmp_path / "applied_jobs.yml"
    existing_urls = {"https://a.com"}
    existing_titles = set()
    jobs = [
        {"title": "PM", "company": "A", "url": "https://a.com"},
        {"title": "PO", "company": "B", "url": "https://b.com"},
    ]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        tracker.mark_processed(jobs, existing_urls, existing_titles)
        reloaded_urls, _ = tracker.load_processed()
    assert reloaded_urls == {"https://a.com", "https://b.com"}


def test_filter_new_jobs_skips_by_title_key(tmp_path):
    # Same company+title should be skipped even with a different URL
    f = tmp_path / "applied_jobs.yml"
    f.write_text(yaml.dump({"applied_titles": ["testco::product manager"]}))
    jobs = [
        {"title": "Product Manager", "company": "TestCo", "url": "https://testco.com/job/99"},
    ]
    with patch.object(tracker, "TRACKER_FILE", str(f)):
        new_jobs, _, _ = tracker.filter_new_jobs(jobs)
    assert len(new_jobs) == 0
