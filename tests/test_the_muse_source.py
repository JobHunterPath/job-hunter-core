"""Tests for sources/the_muse_source.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import requests.exceptions

from job_hunter_core.sources.the_muse_source import fetch_the_muse_jobs


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "the_muse": {
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


def test_fetch_the_muse_jobs_success():
    response_data = {
        "results": [
            {
                "name": "Software Engineer",
                "company": {"name": "ACME"},
                "refs": {"landing_page": "https://www.themuse.com/jobs/acme/software-engineer"},
                "publication_date": "2026-06-01T00:00:00Z",
                "locations": [{"name": "Remote"}],
                "contents": "<p>Great software engineering role.</p>",
            }
        ]
    }
    with (
        patch(
            "job_hunter_core.sources.the_muse_source.load_api_config",
            return_value=_ENABLED_CFG,
        ),
        patch(
            "job_hunter_core.sources.the_muse_source.requests.get",
            return_value=_mock_get(response_data),
        ),
    ):
        jobs = fetch_the_muse_jobs(
            ["Software Engineer"],
            {"EU": {"location": "Europe", "country": "DE"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )
    assert len(jobs) == 1
    assert jobs[0]["source"] == "The Muse"


def test_fetch_the_muse_jobs_http_error():
    with (
        patch(
            "job_hunter_core.sources.the_muse_source.load_api_config",
            return_value=_ENABLED_CFG,
        ),
        patch(
            "job_hunter_core.sources.the_muse_source.requests.get",
            side_effect=requests.exceptions.HTTPError("500 Server Error"),
        ),
    ):
        jobs = fetch_the_muse_jobs(
            ["Software Engineer"],
            {"EU": {"location": "Europe", "country": "DE"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )
    assert jobs == []


def test_fetch_the_muse_jobs_title_filter():
    response_data = {
        "results": [
            {
                "name": "Software Engineer",
                "company": {"name": "Tech Co"},
                "refs": {"landing_page": "https://www.themuse.com/jobs/techco/software-engineer"},
                "publication_date": "2026-06-01T00:00:00Z",
                "locations": [{"name": "Remote"}],
                "contents": "Engineering role.",
            },
            {
                "name": "Marketing Manager",
                "company": {"name": "Marketing Co"},
                "refs": {"landing_page": "https://www.themuse.com/jobs/mktco/marketing-manager"},
                "publication_date": "2026-06-01T00:00:00Z",
                "locations": [{"name": "Remote"}],
                "contents": "Marketing role.",
            },
        ]
    }
    with (
        patch(
            "job_hunter_core.sources.the_muse_source.load_api_config",
            return_value=_ENABLED_CFG,
        ),
        patch(
            "job_hunter_core.sources.the_muse_source.requests.get",
            return_value=_mock_get(response_data),
        ),
    ):
        jobs = fetch_the_muse_jobs(
            ["Software Engineer"],
            {"EU": {"location": "Europe", "country": "DE"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer"


def test_fetch_the_muse_jobs_disabled():
    disabled_cfg = {"http": {"job_boards": {"the_muse": {"enabled": False}}}}
    with (
        patch(
            "job_hunter_core.sources.the_muse_source.load_api_config",
            return_value=disabled_cfg,
        ),
        patch("job_hunter_core.sources.the_muse_source.requests.get") as mock_get,
    ):
        jobs = fetch_the_muse_jobs(["Software Engineer"], {"EU": {}}, {})
    assert jobs == []
    mock_get.assert_not_called()
