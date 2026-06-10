"""Tests for sources/the_muse_source.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter_core.sources.the_muse_source import TheMuseSource


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


class TestTheMuseSource:
    def test_name(self):
        assert TheMuseSource().name == "the_muse"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"the_muse": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.the_muse_source.load_api_config", return_value=disabled
        ):
            assert TheMuseSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        from job_hunter_core.models import JobPosting

        response_data = {
            "results": [
                {
                    "name": "Software Engineer",
                    "company": {"name": "MuseCo"},
                    "refs": {"landing_page": "https://www.themuse.com/jobs/museco/swe"},
                    "publication_date": "2026-06-01T00:00:00Z",
                    "locations": [{"name": "Remote"}],
                    "contents": "Build great things.",
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
            jobs = TheMuseSource().fetch(["Software Engineer"], _REGIONS, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "The Muse"
