"""Tests for new job source modules — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter_core.models import JobPosting
from job_hunter_core.sources.adzuna_source import AdzunaSource
from job_hunter_core.sources.eures_source import EURESSource
from job_hunter_core.sources.glints_source import GlintsSource
from job_hunter_core.sources.gulftalent_source import GulfTalentSource
from job_hunter_core.sources.jobbank_source import JobBankSource
from job_hunter_core.sources.jobicy_source import JobicySource
from job_hunter_core.sources.jobstreet_source import JobStreetSource
from job_hunter_core.sources.jooble_source import JoobleSource
from job_hunter_core.sources.mycareersfuture_source import MyCareersFutureSource
from job_hunter_core.sources.reed_source import ReedSource
from job_hunter_core.sources.remoteok_source import RemoteOKSource
from job_hunter_core.sources.weworkremotely_source import WeWorkRemotelySource
from job_hunter_core.sources.wttj_source import WTTJSource

# ── helpers ──────────────────────────────────────────────────────────────────


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


def _mock_get_bytes(content: bytes, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.content = content
    return resp


def _mock_post(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_REGIONS = {"EU": {"location": "Europe", "country": "DE"}}
_GB_REGIONS = {"GB": {"location": "London", "country": "GB"}}
_EXCL = {"exclusion_rules": {"excluded_title_terms": []}}


# ═══════════════════════════════════════════════════════════════════════════
# Jobicy
# ═══════════════════════════════════════════════════════════════════════════

_JOBICY_CFG = {"http": {"job_boards": {"jobicy": {"enabled": True, "timeout_seconds": 10}}}}

_JOBICY_JOB = {
    "jobTitle": "Software Engineer",
    "companyName": "ACME",
    "url": "https://example.com/1",
    "pubDate": "2026-06-01T00:00:00Z",
    "jobGeo": "Remote",
    "jobDescription": "<p>An engineering role.</p>",
}


class TestJobicySource:
    def test_name(self):
        assert JobicySource().name == "jobicy"

    def test_is_enabled_respects_config(self):
        disabled = {"http": {"job_boards": {"jobicy": {"enabled": False}}}}
        with patch("job_hunter_core.sources.jobicy_source.load_api_config", return_value=disabled):
            assert JobicySource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        get_mock = MagicMock(return_value=_mock_get({"jobs": [_JOBICY_JOB]}))
        with (
            patch(
                "job_hunter_core.sources.jobicy_source.load_api_config",
                return_value=_JOBICY_CFG,
            ),
            patch("job_hunter_core.sources.jobicy_source.reserve_api_call", return_value=True),
            patch("job_hunter_core.sources.jobicy_source.requests.get", get_mock),
        ):
            jobs = JobicySource().fetch(["Software Engineer"], _REGIONS, _EXCL)
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].source == "Jobicy"
        assert get_mock.call_args.kwargs["params"]["geo"] == "germany"

    def test_fetch_omits_invalid_iso_geo(self):
        get_mock = MagicMock(return_value=_mock_get({"jobs": [_JOBICY_JOB]}))
        with (
            patch(
                "job_hunter_core.sources.jobicy_source.load_api_config",
                return_value=_JOBICY_CFG,
            ),
            patch("job_hunter_core.sources.jobicy_source.reserve_api_call", return_value=True),
            patch("job_hunter_core.sources.jobicy_source.requests.get", get_mock),
        ):
            jobs = JobicySource().fetch(
                ["Software Engineer"],
                {"my": {"country": "MY", "location": "Kuala Lumpur"}},
                _EXCL,
            )
        assert len(jobs) == 1
        assert "geo" not in get_mock.call_args.kwargs["params"]

    def test_fetch_returns_empty_when_disabled(self):
        disabled = {"http": {"job_boards": {"jobicy": {"enabled": False}}}}
        with patch("job_hunter_core.sources.jobicy_source.load_api_config", return_value=disabled):
            jobs = JobicySource().fetch(["Software Engineer"], _REGIONS, _EXCL)
        assert jobs == []


# ═══════════════════════════════════════════════════════════════════════════
# RemoteOK
# ═══════════════════════════════════════════════════════════════════════════

_REMOTEOK_CFG = {"http": {"job_boards": {"remoteok": {"enabled": True, "timeout_seconds": 10}}}}

_REMOTEOK_METADATA = {"legal": "see remoteok.com"}

_REMOTEOK_JOB = {
    "position": "Software Engineer",
    "company": "RemoteCo",
    "url": "https://remoteok.com/1",
    "date": "2026-06-01T00:00:00Z",
    "location": "Remote",
    "tags": ["python", "django"],
    "description": "",
}


class TestRemoteOKSource:
    def test_name(self):
        assert RemoteOKSource().name == "remoteok"

    def test_is_enabled_respects_config(self):
        disabled = {"http": {"job_boards": {"remoteok": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.remoteok_source.load_api_config", return_value=disabled
        ):
            assert RemoteOKSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        feed = [_REMOTEOK_METADATA, _REMOTEOK_JOB]
        with (
            patch(
                "job_hunter_core.sources.remoteok_source.load_api_config",
                return_value=_REMOTEOK_CFG,
            ),
            patch(
                "job_hunter_core.sources.remoteok_source.requests.get",
                return_value=_mock_get(feed),
            ),
        ):
            jobs = RemoteOKSource().fetch(["Software Engineer"], _REGIONS, _EXCL)
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].source == "RemoteOK"

    def test_fetch_returns_empty_when_disabled(self):
        disabled = {"http": {"job_boards": {"remoteok": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.remoteok_source.load_api_config", return_value=disabled
        ):
            jobs = RemoteOKSource().fetch(["Software Engineer"], _REGIONS, _EXCL)
        assert jobs == []


# ═══════════════════════════════════════════════════════════════════════════
# WeWorkRemotely
# ═══════════════════════════════════════════════════════════════════════════

_WWR_CFG = {"http": {"job_boards": {"weworkremotely": {"enabled": True, "timeout_seconds": 10}}}}

_WWR_RSS_MATCHING = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>ACME Corp: Software Engineer</title>
      <link>https://weworkremotely.com/job/1</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
      <description>Build great things.</description>
    </item>
    <item>
      <title>OtherCo: Marketing Manager</title>
      <link>https://weworkremotely.com/job/2</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
      <description>Market things.</description>
    </item>
  </channel>
</rss>"""


# ═══════════════════════════════════════════════════════════════════════════
# Jooble
# ═══════════════════════════════════════════════════════════════════════════

_JOOBLE_CFG = {"http": {"job_boards": {"jooble": {"enabled": True, "timeout_seconds": 10}}}}

_JOOBLE_JOB = {
    "title": "Software Engineer",
    "company": "JoobleCo",
    "link": "https://jooble.org/1",
    "updated": "2026-06-01",
    "location": "Berlin",
    "snippet": "A great role.",
}


# ═══════════════════════════════════════════════════════════════════════════
# Adzuna — pagination
# ═══════════════════════════════════════════════════════════════════════════

_ADZUNA_CFG_PAGINATE = {
    "http": {"job_boards": {"adzuna": {"enabled": True, "results_per_page": 2}}}
}

_ADZUNA_JOB = lambda n: {  # noqa: E731
    "title": "Software Engineer",
    "company": {"display_name": f"Co{n}"},
    "redirect_url": f"https://adzuna.com/{n}",
    "created": "2026-06-01T00:00:00Z",
    "location": {"display_name": "Berlin"},
    "description": "A role.",
}

_ADZUNA_GB_REGIONS = {"GB": {"location": "", "country": "GB"}}

_REED_CFG_PAGINATE = {"http": {"job_boards": {"reed": {"enabled": True, "results_wanted": 2}}}}

_REED_JOB = lambda n: {  # noqa: E731
    "jobTitle": "Software Engineer",
    "employerName": f"Co{n}",
    "jobUrl": f"https://reed.co.uk/{n}",
    "date": "01/06/2026",
    "locationName": "London",
    "jobDescription": "A role.",
}


# ═══════════════════════════════════════════════════════════════════════════
# Regional sources — MyCareersFuture / EURES / JobBank / WTTJ / Glints /
#                   GulfTalent / JobStreet
# ═══════════════════════════════════════════════════════════════════════════


def _mock_html(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.text = text
    r.json.return_value = {}
    return r


_EMPTY_CFG = {"http": {"job_boards": {}}}
_CONFIG = {"exclusion_rules": {"excluded_title_terms": []}}


def _disabled(board: str) -> dict:
    return {"http": {"job_boards": {board: {"enabled": False}}}}


# ── Region fixtures ──────────────────────────────────────────────────────────
_SG = {"sg": {"country": "SG", "location": "Singapore"}}
_NL = {"nl": {"country": "NL", "location": "Amsterdam"}}
_CA = {"ca": {"country": "CA", "location": "Toronto"}}
_FR = {"fr": {"country": "FR", "location": "Paris"}}
_ID = {"id": {"country": "ID", "location": "Jakarta"}}
_IE = {"ie": {"country": "IE", "location": "Dublin"}}
_AE = {"ae": {"country": "AE", "location": "Dubai"}}
_SA = {"sa": {"country": "SA", "location": "Riyadh"}}
_MY = {"my": {"country": "MY", "location": "Kuala Lumpur"}}
_DE = {"de": {"country": "DE", "location": "Berlin"}}
_GB = {"gb": {"country": "GB", "location": "London"}}

# ── Data fixtures used by class tests ────────────────────────────────────────

_MCF_RESPONSE = {
    "results": [
        {
            "uuid": "abc-123",
            "title": "Product Manager",
            "postedCompany": {"name": "GovTech"},
            "description": "<p>Lead product strategy.</p>",
            "metadata": {"dates": {"posting": "2026-06-01T00:00:00"}},
            "salary": {"minimum": 6000, "maximum": 9000},
            "address": {"street": "One North"},
        }
    ]
}

_EURES_RESPONSE = {
    "jvs": [
        {
            "header": {
                "id": "EU-12345",
                "title": "Product Manager",
                "employerName": "EuroCorp",
                "placeOfWork": {"city": "Amsterdam", "countryCode": "NL"},
                "startDate": "2026-06-01",
            },
            "jvDescription": {"description": "<p>Lead product in Amsterdam.</p>"},
            "urls": {"applied": "https://eures.europa.eu/en/jobs-and-cts/jv/EU-12345"},
        }
    ]
}

_JB_HTML = """<html><body>
<article class="resultcount">
  <h3><a href="/job-posting/12345">Product Manager</a></h3>
  <span class="business-title">CanadaCorp</span>
  <span class="location">Toronto, ON</span>
  <span class="date">2026-06-01</span>
</article></body></html>"""

_WTTJ_RESPONSE = {
    "jobs": [
        {
            "id": "wttj-pm-1",
            "name": "Product Manager",
            "organization": {"name": "StartupFR", "slug": "startupfr"},
            "slug": "pm-role",
            "published_at": "2026-06-01",
            "office": {"city": "Paris", "country": {"code": "FR"}},
            "description": "Lead our product team.",
        }
    ]
}

_GLINTS_RESPONSE = {
    "data": {
        "jobs": {
            "data": [
                {
                    "id": "gl-101",
                    "title": "Product Manager",
                    "company": {"name": "GlintsCo"},
                    "createdAt": "2026-06-01",
                    "city": {"name": "Singapore"},
                    "country": {"name": "Singapore"},
                }
            ]
        }
    }
}

_GT_HTML = """<html><body>
<div class="job-listing">
  <h2><a class="job-title" href="/jobs/456">Product Manager</a></h2>
  <span class="company-name">GulfCorp</span>
  <span class="location">Dubai, UAE</span>
</div></body></html>"""

_JS_RESPONSE = {
    "data": {
        "jobs": [
            {
                "id": "js-9001",
                "title": "Product Manager",
                "advertiser": {"description": "JobStreetCo"},
                "teaser": "Drive product growth across SEA.",
                "salary": {"min": 5000, "max": 8000},
                "listingDate": "2026-06-01",
            }
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# Class-level JobSourceAdapter tests
# ═══════════════════════════════════════════════════════════════════════════


class TestEURESSource:
    def test_name(self):
        assert EURESSource().name == "eures"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"eures": {"enabled": False}}}}
        with patch("job_hunter_core.sources.eures_source.load_api_config", return_value=disabled):
            assert EURESSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch("job_hunter_core.sources.eures_source.load_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter_core.sources.eures_source.requests.post",
                return_value=_mock_post(_EURES_RESPONSE),
            ),
        ):
            jobs = EURESSource().fetch(["Product Manager"], _NL, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "EURES"


class TestGlintsSource:
    def test_name(self):
        assert GlintsSource().name == "glints"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"glints": {"enabled": False}}}}
        with patch("job_hunter_core.sources.glints_source.load_api_config", return_value=disabled):
            assert GlintsSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch("job_hunter_core.sources.glints_source.load_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter_core.sources.glints_source.requests.get",
                return_value=_mock_get(_GLINTS_RESPONSE),
            ),
        ):
            jobs = GlintsSource().fetch(["Product Manager"], _SG, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Glints"

    def test_fetch_accepts_list_response(self):
        response = [
            {
                "title": "Product Manager",
                "company": {"name": "GlintsCo"},
                "id": "123",
                "city": {"name": "Singapore"},
                "country": {"name": "Singapore"},
                "description": "<p>Own product delivery.</p>",
                "createdAt": "2026-06-01T00:00:00Z",
            }
        ]
        with (
            patch("job_hunter_core.sources.glints_source.load_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter_core.sources.glints_source.requests.get",
                return_value=_mock_get(response),
            ),
        ):
            jobs = GlintsSource().fetch(["Product Manager"], _SG, _CONFIG)
        assert len(jobs) == 1
        assert jobs[0].company == "GlintsCo"

    def test_fetch_stops_at_default_page_cap_when_pages_are_full(self):
        full_page = [
            {
                "id": f"gl-{index}",
                "title": "Product Manager",
                "company": {"name": "GlintsCo"},
                "createdAt": "2026-06-01",
                "city": {"name": "Singapore"},
                "country": {"name": "Singapore"},
            }
            for index in range(30)
        ]
        cfg = {"http": {"job_boards": {"glints": {"enabled": True}}}}
        get_mock = MagicMock(return_value=_mock_get({"data": {"jobs": {"data": full_page}}}))
        with (
            patch("job_hunter_core.sources.glints_source.load_api_config", return_value=cfg),
            patch("job_hunter_core.sources.glints_source.requests.get", get_mock),
        ):
            jobs = GlintsSource().fetch(["Product Manager"], _SG, _CONFIG)
        assert len(jobs) == 90
        assert get_mock.call_count == 3


class TestGulfTalentSource:
    def test_name(self):
        assert GulfTalentSource().name == "gulftalent"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"gulftalent": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.gulftalent_source.load_api_config", return_value=disabled
        ):
            assert GulfTalentSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch(
                "job_hunter_core.sources.gulftalent_source.load_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter_core.sources.gulftalent_source.requests.get",
                return_value=_mock_html(_GT_HTML),
            ),
        ):
            jobs = GulfTalentSource().fetch(["Product Manager"], _AE, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "GulfTalent"


class TestJobBankSource:
    def test_name(self):
        assert JobBankSource().name == "jobbank"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"jobbank": {"enabled": False}}}}
        with patch("job_hunter_core.sources.jobbank_source.load_api_config", return_value=disabled):
            assert JobBankSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch(
                "job_hunter_core.sources.jobbank_source.load_api_config", return_value=_EMPTY_CFG
            ),
            patch(
                "job_hunter_core.sources.jobbank_source.requests.get",
                return_value=_mock_html(_JB_HTML),
            ),
        ):
            jobs = JobBankSource().fetch(["Product Manager"], _CA, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobBank Canada"


class TestJobStreetSource:
    def test_name(self):
        assert JobStreetSource().name == "jobstreet"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"jobstreet": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.jobstreet_source.load_api_config", return_value=disabled
        ):
            assert JobStreetSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch(
                "job_hunter_core.sources.jobstreet_source.load_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter_core.sources.jobstreet_source.requests.get",
                return_value=_mock_get(_JS_RESPONSE),
            ),
        ):
            jobs = JobStreetSource().fetch(["Product Manager"], _MY, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobStreet"

    def test_fetch_uses_same_page_for_playwright_fallback_after_block(self):
        blocked = _mock_get({}, status=403)
        fallback_pages: list[int] = []

        def fallback(_domain, _site_key, _title, page, _timeout_ms):
            fallback_pages.append(page)
            return [{"_stub": True, "_id": "js-1"}]

        with (
            patch(
                "job_hunter_core.sources.jobstreet_source.load_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter_core.sources.jobstreet_source.requests.get",
                return_value=blocked,
            ),
            patch(
                "job_hunter_core.sources.jobstreet_source._fetch_page_playwright",
                fallback,
            ),
        ):
            jobs = JobStreetSource().fetch(["Product Manager"], _MY, _CONFIG)
        assert len(jobs) == 1
        assert fallback_pages == [1]


class TestMyCareersFutureSource:
    def test_name(self):
        assert MyCareersFutureSource().name == "mycareersfuture"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"mycareersfuture": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.mycareersfuture_source.load_api_config",
            return_value=disabled,
        ):
            assert MyCareersFutureSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch(
                "job_hunter_core.sources.mycareersfuture_source.load_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter_core.sources.mycareersfuture_source.requests.get",
                return_value=_mock_get(_MCF_RESPONSE),
            ),
        ):
            jobs = MyCareersFutureSource().fetch(["Product Manager"], _SG, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "MyCareersFuture"


class TestWeWorkRemotelySource:
    def test_name(self):
        assert WeWorkRemotelySource().name == "weworkremotely"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"weworkremotely": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.weworkremotely_source.load_api_config", return_value=disabled
        ):
            assert WeWorkRemotelySource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch(
                "job_hunter_core.sources.weworkremotely_source.load_api_config",
                return_value=_WWR_CFG,
            ),
            patch(
                "job_hunter_core.sources.weworkremotely_source.requests.get",
                return_value=_mock_get_bytes(_WWR_RSS_MATCHING),
            ),
        ):
            jobs = WeWorkRemotelySource().fetch(["Software Engineer"], _REGIONS, _EXCL)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "WeWorkRemotely"


class TestWTTJSource:
    def test_name(self):
        assert WTTJSource().name == "wttj"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"wttj": {"enabled": False}}}}
        with patch("job_hunter_core.sources.wttj_source.load_api_config", return_value=disabled):
            assert WTTJSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        with (
            patch("job_hunter_core.sources.wttj_source.load_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter_core.sources.wttj_source.requests.get",
                return_value=_mock_get(_WTTJ_RESPONSE),
            ),
        ):
            jobs = WTTJSource().fetch(["Product Manager"], _FR, _CONFIG)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Welcome to the Jungle"


class TestReedSource:
    def test_name(self):
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        assert src.name == "reed"

    def test_is_enabled_false_when_disabled(self):
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        disabled = {"http": {"job_boards": {"reed": {"enabled": False}}}}
        with patch("job_hunter_core.sources.reed_source.load_api_config", return_value=disabled):
            assert src.is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        cfg = {"http": {"job_boards": {"reed": {"enabled": True, "results_wanted": 1}}}}
        page_data = {"results": [_REED_JOB(1)]}
        with (
            patch("job_hunter_core.sources.reed_source.load_api_config", return_value=cfg),
            patch("job_hunter_core.sources.reed_source.reserve_api_call", return_value=True),
            patch(
                "job_hunter_core.sources.reed_source.requests.get",
                return_value=_mock_get(page_data),
            ),
        ):
            jobs = src.fetch(["Software Engineer"], _GB_REGIONS, _EXCL)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Reed"


class TestAdzunaSource:
    def test_name(self):
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        assert src.name == "adzuna"

    def test_is_enabled_false_when_disabled(self):
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        disabled = {"http": {"job_boards": {"adzuna": {"enabled": False}}}}
        with patch("job_hunter_core.sources.adzuna_source.load_api_config", return_value=disabled):
            assert src.is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        cfg = {"http": {"job_boards": {"adzuna": {"enabled": True, "results_per_page": 1}}}}
        page_data = {"results": [_ADZUNA_JOB(1)]}
        with (
            patch("job_hunter_core.sources.adzuna_source.load_api_config", return_value=cfg),
            patch("job_hunter_core.sources.adzuna_source.reserve_api_call", return_value=True),
            patch(
                "job_hunter_core.sources.adzuna_source.requests.get",
                return_value=_mock_get(page_data),
            ),
        ):
            jobs = src.fetch(["Software Engineer"], _ADZUNA_GB_REGIONS, _EXCL)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Adzuna"


class TestJoobleSource:
    def test_name(self):
        src = JoobleSource.__new__(JoobleSource)
        src._api_key = "test-key"
        assert src.name == "jooble"

    def test_is_enabled_false_when_disabled(self):
        src = JoobleSource.__new__(JoobleSource)
        src._api_key = "test-key"
        disabled = {"http": {"job_boards": {"jooble": {"enabled": False}}}}
        with patch("job_hunter_core.sources.jooble_source.load_api_config", return_value=disabled):
            assert src.is_enabled({}) is False

    def test_fetch_returns_job_postings(self):
        src = JoobleSource.__new__(JoobleSource)
        src._api_key = "test-key"
        with (
            patch(
                "job_hunter_core.sources.jooble_source.load_api_config",
                return_value=_JOOBLE_CFG,
            ),
            patch("job_hunter_core.sources.jooble_source.reserve_api_call", return_value=True),
            patch(
                "job_hunter_core.sources.jooble_source.requests.post",
                return_value=_mock_post({"jobs": [_JOOBLE_JOB]}),
            ),
        ):
            jobs = src.fetch(["Software Engineer"], _REGIONS, _EXCL)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Jooble"
