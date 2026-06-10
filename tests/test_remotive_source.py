"""Tests for sources/remotive_source.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import requests.exceptions

from job_hunter_core.models import JobPosting
from job_hunter_core.sources.remotive_source import RemotiveSource, fetch_remotive_jobs


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "remotive": {
                "enabled": True,
                "timeout_seconds": 10,
                "max_pages_per_query": 1,
            }
        }
    }
}

_REGIONS = {
    "EU": {"location": "Europe", "country": "DE"},
}

_CONFIG = {"exclusion_rules": {"excluded_title_terms": []}}


def test_fetch_remotive_jobs_success():
    response_data = {
        "jobs": [
            {
                "title": "Software Engineer",
                "company_name": "ACME",
                "url": "https://example.com/job/1",
                "publication_date": "2026-06-01",
                "candidate_required_location": "Remote",
                "description": "<p>Some job</p>",
            }
        ]
    }
    with (
        patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value=_ENABLED_CFG,
        ),
        patch(
            "job_hunter_core.sources.remotive_source.requests.get",
            return_value=_mock_get(response_data),
        ),
    ):
        jobs = fetch_remotive_jobs(
            ["Software Engineer"],
            {"EU": {"location": "Europe", "country": "DE"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer"
    assert jobs[0]["source"] == "Remotive"


def test_fetch_remotive_jobs_http_error():
    with (
        patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value=_ENABLED_CFG,
        ),
        patch(
            "job_hunter_core.sources.remotive_source.requests.get",
            side_effect=requests.exceptions.HTTPError("500 Server Error"),
        ),
    ):
        jobs = fetch_remotive_jobs(
            ["Software Engineer"],
            {"EU": {"location": "Europe", "country": "DE"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )
    assert jobs == []


def test_fetch_remotive_jobs_title_filter():
    response_data = {
        "jobs": [
            {
                "title": "Software Engineer",
                "company_name": "Tech Co",
                "url": "https://example.com/job/1",
                "publication_date": "2026-06-01",
                "candidate_required_location": "Remote",
                "description": "Engineering role.",
            },
            {
                "title": "Marketing Manager",
                "company_name": "Marketing Co",
                "url": "https://example.com/job/2",
                "publication_date": "2026-06-01",
                "candidate_required_location": "Remote",
                "description": "Marketing role.",
            },
        ]
    }
    with (
        patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value=_ENABLED_CFG,
        ),
        patch(
            "job_hunter_core.sources.remotive_source.requests.get",
            return_value=_mock_get(response_data),
        ),
    ):
        jobs = fetch_remotive_jobs(
            ["Software Engineer"],
            {"EU": {"location": "Europe", "country": "DE"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer"


def test_fetch_remotive_jobs_disabled():
    disabled_cfg = {"http": {"job_boards": {"remotive": {"enabled": False}}}}
    with (
        patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value=disabled_cfg,
        ),
        patch("job_hunter_core.sources.remotive_source.requests.get") as mock_get,
    ):
        jobs = fetch_remotive_jobs(["Software Engineer"], {"EU": {}}, {})
    assert jobs == []
    mock_get.assert_not_called()


def test_fetch_remotive_jobs_defaults_enabled():
    response_data = {
        "jobs": [
            {
                "title": "Software Engineer",
                "company_name": "ACME",
                "url": "https://example.com/job/1",
                "publication_date": "2026-06-01",
                "candidate_required_location": "Remote",
                "description": "Engineering role.",
            }
        ]
    }
    with (
        patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value={"http": {"job_boards": {}}},
        ),
        patch(
            "job_hunter_core.sources.remotive_source.requests.get",
            return_value=_mock_get(response_data),
        ) as mock_get,
    ):
        jobs = fetch_remotive_jobs(["Software Engineer"], _REGIONS, _CONFIG)
    assert len(jobs) == 1
    mock_get.assert_called_once()


class TestRemotiveSource:
    def test_name(self):
        assert RemotiveSource().name == "remotive"

    def test_is_enabled_respects_config(self):
        disabled_cfg = {"http": {"job_boards": {"remotive": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value=disabled_cfg,
        ):
            assert RemotiveSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        response_data = {
            "jobs": [
                {
                    "title": "Software Engineer",
                    "company_name": "ACME",
                    "url": "https://example.com/job/1",
                    "publication_date": "2026-06-01",
                    "candidate_required_location": "Remote",
                    "description": "<p>Some job</p>",
                }
            ]
        }
        with (
            patch(
                "job_hunter_core.sources.remotive_source.load_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter_core.sources.remotive_source.requests.get",
                return_value=MagicMock(
                    raise_for_status=MagicMock(), **{"json.return_value": response_data}
                ),
            ),
        ):
            jobs = RemotiveSource().fetch(["Software Engineer"], _REGIONS, _CONFIG)
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].source == "Remotive"

    def test_fetch_returns_empty_when_disabled(self):
        disabled_cfg = {"http": {"job_boards": {"remotive": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.remotive_source.load_api_config",
            return_value=disabled_cfg,
        ):
            jobs = RemotiveSource().fetch(["Software Engineer"], _REGIONS, _CONFIG)
        assert jobs == []
