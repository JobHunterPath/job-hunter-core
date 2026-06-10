"""Tests for sources/himalayas_source.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter_core.sources import himalayas_source as hm


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "himalayas": {
                "enabled": True,
                "timeout_seconds": 10,
                "max_pages_per_query": 1,
            }
        }
    }
}

_REGIONS = {
    "global_remote": {"country": "DE", "location": ""},
}

_CONFIG = {"exclusion_rules": {"excluded_title_terms": []}}

_RESPONSE = {
    "jobs": [
        {
            "title": "Product Manager",
            "companyName": "Remote Corp",
            "applicationLink": "https://himalayas.app/jobs/pm-123",
            "pubDate": 1714521600000,
            "locationRestrictions": [{"alpha2": "DE", "name": "Germany"}],
            "description": "<p>Great remote PM role.</p>",
        },
        {
            "title": "Sales Director",
            "companyName": "Other Co",
            "applicationLink": "https://himalayas.app/jobs/sd-999",
            "pubDate": 1714521600000,
            "locationRestrictions": [{"alpha2": "US", "name": "United States"}],
            "description": "US only.",
        },
    ]
}


def test_posted_from_timestamp():
    assert hm._posted(1714521600000) == "2024-05-01"


def test_posted_from_string():
    assert hm._posted("2026-05-01T12:00:00Z") == "2026-05-01"


def test_posted_unknown():
    assert hm._posted(None) == ""


def test_location_text_remote_fallback():
    assert hm._location_text({}) == "Remote"


def test_location_text_with_restrictions():
    job = {"locationRestrictions": [{"alpha2": "DE", "name": "Germany"}]}
    assert hm._location_text(job) == "Germany"


def test_country_matches_no_restrictions():
    assert hm._country_matches({}, "DE") is True


def test_country_matches_matching():
    job = {"locationRestrictions": [{"alpha2": "DE"}]}
    assert hm._country_matches(job, "DE") is True


def test_country_matches_no_match():
    job = {"locationRestrictions": [{"alpha2": "US"}]}
    assert hm._country_matches(job, "DE") is False


class TestHimalayasSource:
    def test_name(self):
        assert hm.HimalayasSource().name == "himalayas"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"himalayas": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.himalayas_source.load_api_config", return_value=disabled
        ):
            assert hm.HimalayasSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        from job_hunter_core.models import JobPosting

        with (
            patch(
                "job_hunter_core.sources.himalayas_source.load_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter_core.sources.himalayas_source.requests.get",
                return_value=_mock_get(_RESPONSE),
            ),
        ):
            jobs = hm.HimalayasSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Himalayas"
