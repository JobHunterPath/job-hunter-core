"""Tests for sources/job_boards.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from job_hunter_core.core import api_budget
from job_hunter_core.models import JobPosting
from job_hunter_core.sources import job_boards
from job_hunter_core.sources.job_boards import ArbeitnowSource, JSearchSource


def _mock_get(data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


class ErrorResponse:
    def __init__(self, status_code: int, text: str = "", reason: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.reason = reason

    def raise_for_status(self) -> None:
        raise job_boards.requests.exceptions.HTTPError(response=self)

    def json(self) -> dict:
        return {}


@pytest.fixture(autouse=True)
def reset_jsearch_failure_state():
    job_boards._JSEARCH_FAILURES = 0
    yield
    job_boards._JSEARCH_FAILURES = 0


ARBEITNOW_JOB = {
    "slug": "pm-berlin-testco",
    "company_name": "TestCo",
    "title": "Product Manager",
    "description": "<p>Great PM role in Berlin.</p>",
    "tags": ["product", "berlin"],
    "job_types": ["full-time"],
    "location": "Berlin, Germany",
    "remote": False,
    "url": "https://www.arbeitnow.com/jobs/testco/product-manager-berlin",
    "created_at": 1745000000,
}

ARBEITNOW_PAGE = {"data": [ARBEITNOW_JOB], "links": {}, "meta": {}}
ARBEITNOW_EMPTY = {"data": [], "links": {}, "meta": {}}

JSEARCH_JOB = {
    "employer_name": "TestCo",
    "job_title": "Product Manager",
    "job_apply_link": "https://linkedin.com/jobs/view/12345",
    "job_description": "Great PM role.",
    "job_city": "Berlin",
    "job_country": "DE",
    "job_posted_at_datetime_utc": "2026-04-01T00:00:00.000Z",
}

JSEARCH_RESPONSE = {"status": "OK", "data": [JSEARCH_JOB]}


# ── ArbeitnowSource ──────────────────────────────────────────────────────────

_ENABLED_ARBEITNOW_CFG = {"http": {"job_boards": {"arbeitnow": {"enabled": True}}}}
_REGIONS = {"DE": {"location": "Berlin", "country": "DE"}}
_CONFIG = {"exclusion_rules": {"excluded_title_terms": []}}


class TestArbeitnowSource:
    def test_name(self):
        assert ArbeitnowSource().name == "arbeitnow"

    def test_is_enabled_respects_config(self):
        disabled_cfg = {"http": {"job_boards": {"arbeitnow": {"enabled": False}}}}
        with patch("job_hunter_core.sources.job_boards.load_api_config", return_value=disabled_cfg):
            assert ArbeitnowSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert len(postings) == 1
        assert isinstance(postings[0], JobPosting)
        assert postings[0].source == "Arbeitnow"
        assert postings[0].region == "DE"

    def test_fetch_returns_empty_when_disabled(self):
        disabled_cfg = {"http": {"job_boards": {"arbeitnow": {"enabled": False}}}}
        with patch("job_hunter_core.sources.job_boards.load_api_config", return_value=disabled_cfg):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings == []

    def test_fetch_filters_by_title_and_location(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Owner"], _REGIONS, _CONFIG)
        assert postings == []

    def test_fetch_returns_correct_fields(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        posting = postings[0]
        assert posting.company == "TestCo"
        assert posting.url == ARBEITNOW_JOB["url"]
        assert "Berlin" in posting.snippet

    def test_fetch_strips_html(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert "<p>" not in postings[0].snippet

    def test_fetch_parses_unix_timestamp(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings[0].posted != ""
        assert len(postings[0].posted) == 10

    def test_fetch_parses_iso_date(self):
        job = {**ARBEITNOW_JOB, "created_at": "2026-04-15T10:00:00Z"}
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get({"data": [job]}),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings[0].posted == "2026-04-15"

    def test_fetch_uses_code_owned_single_page_cap(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(ARBEITNOW_PAGE),
            ) as mock_get,
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert len(postings) == 1
        assert mock_get.call_count == 1

    def test_fetch_returns_empty_on_api_error(self):
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                side_effect=Exception("timeout"),
            ),
        ):
            postings = ArbeitnowSource().fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings == []


# ── JSearchSource ─────────────────────────────────────────────────────────────

_ENABLED_JSEARCH_CFG = {"http": {"job_boards": {"jsearch": {"enabled": True, "num_pages": 1}}}}


class TestJSearchSource:
    def test_name(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        assert src.name == "jsearch"

    def test_is_enabled_false_without_key(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = ""
        assert src.is_enabled({}) is False

    def test_fetch_returns_empty_without_key(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = ""
        postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings == []

    def test_fetch_returns_job_postings(self, tmp_path):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        import job_hunter_core.core.api_budget as _budget

        with (
            patch.object(_budget, "ROOT", tmp_path),
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(JSEARCH_RESPONSE),
            ),
        ):
            postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert len(postings) == 1
        assert isinstance(postings[0], JobPosting)
        assert postings[0].source == "JSearch"
        assert postings[0].region == "DE"

    def test_fetch_returns_empty_when_disabled(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        disabled_cfg = {"http": {"job_boards": {"jsearch": {"enabled": False}}}}
        with patch("job_hunter_core.sources.job_boards.load_api_config", return_value=disabled_cfg):
            postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings == []

    def test_fetch_returns_correct_fields(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(JSEARCH_RESPONSE),
            ),
        ):
            postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        posting = postings[0]
        assert posting.company == "TestCo"
        assert posting.url == "https://linkedin.com/jobs/view/12345"
        assert posting.posted == "2026-04-01"
        assert "Berlin" in posting.snippet

    def test_fetch_includes_location_in_query(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(JSEARCH_RESPONSE),
            ) as mock_get,
        ):
            src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        call_params = mock_get.call_args[1]["params"]
        assert "Berlin" in call_params["query"]

    def test_fetch_uses_country_and_language(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        regions_with_lang = {"DE": {"location": "Berlin", "country": "DE", "search_lang": "en"}}
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(JSEARCH_RESPONSE),
            ) as mock_get,
        ):
            src.fetch(["Product Manager"], regions_with_lang, _CONFIG)
        call_params = mock_get.call_args[1]["params"]
        assert call_params["country"] == "de"
        assert call_params["language"] == "en"

    def test_fetch_excludes_terms(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        job = {**JSEARCH_JOB, "job_title": "Product Engineer"}
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get({"status": "OK", "data": [job]}),
            ) as mock_get,
        ):
            postings = src.fetch(
                ["Product Manager"],
                _REGIONS,
                _CONFIG,
                excluded_title_terms=["engineer", "working student"],
            )
        assert postings == []
        call_params = mock_get.call_args[1]["params"]
        assert '-"engineer"' in call_params["query"]
        assert '-"working student"' in call_params["query"]

    def test_fetch_one_request_per_title(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(JSEARCH_RESPONSE),
            ) as mock_get,
        ):
            src.fetch(["Product Manager", "Product Owner"], _REGIONS, _CONFIG)
        assert mock_get.call_count == 2

    def test_fetch_handles_missing_city(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        job = {**JSEARCH_JOB, "job_city": None, "job_country": None}
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get({"status": "OK", "data": [job]}),
            ),
        ):
            postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert len(postings) == 1
        assert postings[0].snippet == job["job_description"]

    def test_fetch_suppressed_after_failures(self, reset_jsearch_failure_state):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        config = {
            "http": {
                "job_boards": {
                    "max_consecutive_failures": 3,
                    "jsearch": {"enabled": True, "num_pages": 1},
                }
            }
        }
        with (
            patch("job_hunter_core.sources.job_boards.load_api_config", return_value=config),
            patch(
                "job_hunter_core.sources.job_boards.requests.get", side_effect=Exception("limit")
            ) as mock_get,
        ):
            for _ in range(4):
                postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
                assert postings == []
        assert mock_get.call_count == 3

    def test_fetch_resets_failure_count(self):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        job_boards._JSEARCH_FAILURES = 2
        with (
            patch(
                "job_hunter_core.sources.job_boards.load_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter_core.sources.job_boards.requests.get",
                return_value=_mock_get(JSEARCH_RESPONSE),
            ),
        ):
            postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert len(postings) == 1
        assert job_boards._JSEARCH_FAILURES == 0

    def test_fetch_budget_cap_skips_http(self, monkeypatch: pytest.MonkeyPatch):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        monkeypatch.setattr(job_boards, "reserve_api_call", lambda _provider: False)
        monkeypatch.setattr(
            job_boards.requests,
            "get",
            lambda *args, **kwargs: pytest.fail("HTTP should not run"),
        )
        with patch(
            "job_hunter_core.sources.job_boards.load_api_config",
            return_value=_ENABLED_JSEARCH_CFG,
        ):
            postings = src.fetch(["Product Manager"], _REGIONS, _CONFIG)
        assert postings == []

    def test_fetch_quota_error_disables(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        monkeypatch.setattr(api_budget, "ROOT", tmp_path)
        calls = {"count": 0}

        def fake_get(*args, **kwargs):
            calls["count"] += 1
            return ErrorResponse(429, text="Monthly quota exceeded")

        monkeypatch.setattr(job_boards.requests, "get", fake_get)

        with patch(
            "job_hunter_core.sources.job_boards.load_api_config",
            return_value=_ENABLED_JSEARCH_CFG,
        ):
            assert src.fetch(["Product Manager"], _REGIONS, _CONFIG) == []
            assert src.fetch(["Product Manager"], _REGIONS, _CONFIG) == []
        assert calls["count"] == 1
