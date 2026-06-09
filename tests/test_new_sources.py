"""Tests for new job source modules — all HTTP calls are mocked."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests.exceptions

from job_hunter_core.sources.adzuna_source import fetch_adzuna_jobs
from job_hunter_core.sources.eures_source import fetch_eures_jobs
from job_hunter_core.sources.glints_source import fetch_glints_jobs
from job_hunter_core.sources.gulftalent_source import fetch_gulftalent_jobs
from job_hunter_core.sources.irishjobs_source import fetch_irishjobs_jobs
from job_hunter_core.sources.jobbank_source import fetch_jobbank_jobs
from job_hunter_core.sources.jobicy_source import fetch_jobicy_jobs
from job_hunter_core.sources.jobspy_source import fetch_jobspy_jobs
from job_hunter_core.sources.jobstreet_source import fetch_jobstreet_jobs
from job_hunter_core.sources.jooble_source import fetch_jooble_jobs
from job_hunter_core.sources.mycareersfuture_source import fetch_mycareersfuture_jobs
from job_hunter_core.sources.naukrigulf_source import fetch_naukrigulf_jobs
from job_hunter_core.sources.reed_source import fetch_reed_jobs
from job_hunter_core.sources.remoteok_source import fetch_remoteok_jobs
from job_hunter_core.sources.weworkremotely_source import fetch_weworkremotely_jobs
from job_hunter_core.sources.wttj_source import fetch_wttj_jobs

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


def test_jobicy_happy_path():
    with (
        patch("job_hunter_core.sources.jobicy_source.load_api_config", return_value=_JOBICY_CFG),
        patch("job_hunter_core.sources.jobicy_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.jobicy_source.requests.get",
            return_value=_mock_get({"jobs": [_JOBICY_JOB]}),
        ),
    ):
        jobs = fetch_jobicy_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Software Engineer"
    assert j["company"] == "ACME"
    assert j["source"] == "Jobicy"
    assert j["region"] == "EU"
    assert j["query"] == "Software Engineer @ EU"
    assert j["location"] == "Remote"


def test_jobicy_malformed_response():
    with (
        patch("job_hunter_core.sources.jobicy_source.load_api_config", return_value=_JOBICY_CFG),
        patch("job_hunter_core.sources.jobicy_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.jobicy_source.requests.get",
            return_value=_mock_get({"jobs": "not-a-list"}),
        ),
    ):
        jobs = fetch_jobicy_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []


def test_jobicy_title_filter():
    jobs_data = [
        {**_JOBICY_JOB, "jobTitle": "Software Engineer"},
        {**_JOBICY_JOB, "jobTitle": "Marketing Manager", "url": "https://example.com/2"},
    ]
    with (
        patch("job_hunter_core.sources.jobicy_source.load_api_config", return_value=_JOBICY_CFG),
        patch("job_hunter_core.sources.jobicy_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.jobicy_source.requests.get",
            return_value=_mock_get({"jobs": jobs_data}),
        ),
    ):
        jobs = fetch_jobicy_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer"


def test_jobicy_disabled():
    disabled = {"http": {"job_boards": {"jobicy": {"enabled": False}}}}
    with (
        patch("job_hunter_core.sources.jobicy_source.load_api_config", return_value=disabled),
        patch("job_hunter_core.sources.jobicy_source.requests.get") as mock_get,
    ):
        jobs = fetch_jobicy_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []
    mock_get.assert_not_called()


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


def test_remoteok_happy_path():
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
        jobs = fetch_remoteok_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Software Engineer"
    assert j["company"] == "RemoteCo"
    assert j["source"] == "RemoteOK"
    assert j["region"] == "EU"


def test_remoteok_skips_metadata_element():
    # Metadata is element [0]; any non-matching title should be in [1]
    non_matching = {**_REMOTEOK_JOB, "position": "Marketing Manager"}
    feed = [_REMOTEOK_METADATA, non_matching]
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
        jobs = fetch_remoteok_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []


def test_remoteok_malformed_non_list():
    with (
        patch(
            "job_hunter_core.sources.remoteok_source.load_api_config",
            return_value=_REMOTEOK_CFG,
        ),
        patch(
            "job_hunter_core.sources.remoteok_source.requests.get",
            return_value=_mock_get({"error": "bad"}),
        ),
    ):
        jobs = fetch_remoteok_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []


def test_remoteok_title_filter():
    feed = [
        _REMOTEOK_METADATA,
        {**_REMOTEOK_JOB, "position": "Software Engineer"},
        {**_REMOTEOK_JOB, "position": "Data Scientist", "url": "https://remoteok.com/2"},
    ]
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
        jobs = fetch_remoteok_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Software Engineer"


def test_remoteok_disabled():
    disabled = {"http": {"job_boards": {"remoteok": {"enabled": False}}}}
    with (
        patch(
            "job_hunter_core.sources.remoteok_source.load_api_config",
            return_value=disabled,
        ),
        patch("job_hunter_core.sources.remoteok_source.requests.get") as mock_get,
    ):
        jobs = fetch_remoteok_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []
    mock_get.assert_not_called()


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


def test_wwr_happy_path():
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
        jobs = fetch_weworkremotely_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Software Engineer"
    assert j["company"] == "ACME Corp"
    assert j["source"] == "WeWorkRemotely"
    assert j["location"] == "Remote"
    assert j["region"] == "EU"
    assert j["posted"] == "2026-06-01"


def test_wwr_malformed_xml():
    with (
        patch(
            "job_hunter_core.sources.weworkremotely_source.load_api_config",
            return_value=_WWR_CFG,
        ),
        patch(
            "job_hunter_core.sources.weworkremotely_source.requests.get",
            return_value=_mock_get_bytes(b"not xml at all <<<"),
        ),
    ):
        jobs = fetch_weworkremotely_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []


def test_wwr_title_filter():
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
        jobs = fetch_weworkremotely_jobs(["Software Engineer"], _REGIONS, _EXCL)

    titles = [j["title"] for j in jobs]
    assert "Marketing Manager" not in titles
    assert "Software Engineer" in titles


def test_wwr_disabled():
    disabled = {"http": {"job_boards": {"weworkremotely": {"enabled": False}}}}
    with (
        patch(
            "job_hunter_core.sources.weworkremotely_source.load_api_config",
            return_value=disabled,
        ),
        patch("job_hunter_core.sources.weworkremotely_source.requests.get") as mock_get,
    ):
        jobs = fetch_weworkremotely_jobs(["Software Engineer"], _REGIONS, _EXCL)

    assert jobs == []
    mock_get.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Jooble
# ═══════════════════════════════════════════════════════════════════════════

_JOOBLE_CFG = {
    "http": {
        "job_boards": {"jooble": {"enabled": True, "timeout_seconds": 10, "max_pages_per_query": 3}}
    }
}

_JOOBLE_JOB = {
    "title": "Software Engineer",
    "company": "JoobleCo",
    "link": "https://jooble.org/1",
    "updated": "2026-06-01",
    "location": "Berlin",
    "snippet": "A great role.",
}


def test_jooble_happy_path():
    with (
        patch("job_hunter_core.sources.jooble_source.load_api_config", return_value=_JOOBLE_CFG),
        patch("job_hunter_core.sources.jooble_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.jooble_source.requests.post",
            return_value=_mock_post({"jobs": [_JOOBLE_JOB]}),
        ),
    ):
        jobs = fetch_jooble_jobs(["Software Engineer"], _REGIONS, _EXCL, api_key="test-key")

    assert len(jobs) >= 1
    j = jobs[0]
    assert j["title"] == "Software Engineer"
    assert j["company"] == "JoobleCo"
    assert j["source"] == "Jooble"
    assert j["region"] == "EU"
    assert j["url"] == "https://jooble.org/1"


def test_jooble_missing_key_returns_empty():
    jobs = fetch_jooble_jobs(["Software Engineer"], _REGIONS, _EXCL, api_key="")
    assert jobs == []


def test_jooble_pagination_stops_on_empty_page():
    page1 = {"jobs": [_JOOBLE_JOB, {**_JOOBLE_JOB, "link": "https://jooble.org/2"}]}
    page2 = {"jobs": []}

    responses = [_mock_post(page1), _mock_post(page2)]

    with (
        patch("job_hunter_core.sources.jooble_source.load_api_config", return_value=_JOOBLE_CFG),
        patch("job_hunter_core.sources.jooble_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.jooble_source.requests.post",
            side_effect=responses,
        ) as mock_post,
    ):
        jobs = fetch_jooble_jobs(["Software Engineer"], _REGIONS, _EXCL, api_key="test-key")

    # Page 1 called, page 2 called (empty → break), page 3 never called
    assert mock_post.call_count == 2
    assert len(jobs) == 2


def test_jooble_title_filter():
    jobs_data = [
        {**_JOOBLE_JOB, "title": "Software Engineer"},
        {**_JOOBLE_JOB, "title": "Marketing Manager", "link": "https://jooble.org/2"},
    ]
    with (
        patch("job_hunter_core.sources.jooble_source.load_api_config", return_value=_JOOBLE_CFG),
        patch("job_hunter_core.sources.jooble_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.jooble_source.requests.post",
            return_value=_mock_post({"jobs": jobs_data}),
        ),
    ):
        jobs = fetch_jooble_jobs(["Software Engineer"], _REGIONS, _EXCL, api_key="test-key")

    assert all(j["title"] == "Software Engineer" for j in jobs)


def test_jooble_disabled():
    disabled = {"http": {"job_boards": {"jooble": {"enabled": False}}}}
    with (
        patch("job_hunter_core.sources.jooble_source.load_api_config", return_value=disabled),
        patch("job_hunter_core.sources.jooble_source.requests.post") as mock_post,
    ):
        jobs = fetch_jooble_jobs(["Software Engineer"], _REGIONS, _EXCL, api_key="test-key")

    assert jobs == []
    mock_post.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Adzuna — pagination
# ═══════════════════════════════════════════════════════════════════════════

_ADZUNA_CFG_PAGINATE = {
    "http": {
        "job_boards": {"adzuna": {"enabled": True, "results_per_page": 2, "max_pages_per_query": 3}}
    }
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


def test_adzuna_pagination_stops_when_page_is_empty():
    page1 = {"results": [_ADZUNA_JOB(1), _ADZUNA_JOB(2)]}  # full (2 == results_per_page)
    page2 = {"results": []}  # empty → break

    with (
        patch(
            "job_hunter_core.sources.adzuna_source.load_api_config",
            return_value=_ADZUNA_CFG_PAGINATE,
        ),
        patch("job_hunter_core.sources.adzuna_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.adzuna_source.requests.get",
            side_effect=[_mock_get(page1), _mock_get(page2)],
        ) as mock_get,
    ):
        jobs = fetch_adzuna_jobs(
            ["Software Engineer"],
            _ADZUNA_GB_REGIONS,
            _EXCL,
            app_id="app123",
            api_key="key123",
        )

    assert mock_get.call_count == 2
    assert len(jobs) == 2


def test_adzuna_stops_when_page_is_underfull():
    # Page 1 returns only 1 result (< results_per_page=2) → break immediately
    page1 = {"results": [_ADZUNA_JOB(1)]}

    with (
        patch(
            "job_hunter_core.sources.adzuna_source.load_api_config",
            return_value=_ADZUNA_CFG_PAGINATE,
        ),
        patch("job_hunter_core.sources.adzuna_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.adzuna_source.requests.get",
            return_value=_mock_get(page1),
        ) as mock_get,
    ):
        jobs = fetch_adzuna_jobs(
            ["Software Engineer"],
            _ADZUNA_GB_REGIONS,
            _EXCL,
            app_id="app123",
            api_key="key123",
        )

    assert mock_get.call_count == 1
    assert len(jobs) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Reed — pagination
# ═══════════════════════════════════════════════════════════════════════════

_REED_CFG_PAGINATE = {
    "http": {
        "job_boards": {"reed": {"enabled": True, "results_wanted": 2, "max_pages_per_query": 3}}
    }
}

_REED_JOB = lambda n: {  # noqa: E731
    "jobTitle": "Software Engineer",
    "employerName": f"Co{n}",
    "jobUrl": f"https://reed.co.uk/{n}",
    "date": "01/06/2026",
    "locationName": "London",
    "jobDescription": "A role.",
}


def test_reed_pagination_stops_when_page_is_empty():
    page1 = {"results": [_REED_JOB(1), _REED_JOB(2)]}
    page2 = {"results": []}

    with (
        patch(
            "job_hunter_core.sources.reed_source.load_api_config",
            return_value=_REED_CFG_PAGINATE,
        ),
        patch("job_hunter_core.sources.reed_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.reed_source.requests.get",
            side_effect=[_mock_get(page1), _mock_get(page2)],
        ) as mock_get,
    ):
        jobs = fetch_reed_jobs(
            ["Software Engineer"],
            _GB_REGIONS,
            _EXCL,
            api_key="reedkey",
        )

    assert mock_get.call_count == 2
    assert len(jobs) == 2


def test_reed_stops_when_page_is_underfull():
    page1 = {"results": [_REED_JOB(1)]}

    with (
        patch(
            "job_hunter_core.sources.reed_source.load_api_config",
            return_value=_REED_CFG_PAGINATE,
        ),
        patch("job_hunter_core.sources.reed_source.reserve_api_call", return_value=True),
        patch(
            "job_hunter_core.sources.reed_source.requests.get",
            return_value=_mock_get(page1),
        ) as mock_get,
    ):
        jobs = fetch_reed_jobs(
            ["Software Engineer"],
            _GB_REGIONS,
            _EXCL,
            api_key="reedkey",
        )

    assert mock_get.call_count == 1
    assert len(jobs) == 1


# ═══════════════════════════════════════════════════════════════════════════
# JobSpy — sites config override
# ═══════════════════════════════════════════════════════════════════════════


def test_jobspy_sites_config_override(monkeypatch):
    """When sites is set in config, scrape_jobs receives exactly those sites."""
    calls = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        import pandas as pd

        return pd.DataFrame(
            columns=["title", "company", "job_url", "date_posted", "description", "site"]
        )

    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=fake_scrape_jobs))

    cfg = {
        "http": {
            "job_boards": {
                "jobspy": {
                    "enabled": True,
                    "results_per_query": 5,
                    "hours_old": 72,
                    "glassdoor_enabled": False,
                    "linkedin_enabled": False,
                    "linkedin_fetch_description": False,
                    "sites": ["google", "zip_recruiter"],
                }
            }
        }
    }

    with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=cfg):
        fetch_jobspy_jobs(
            ["Software Engineer"],
            {"DE": {"country": "DE", "location": "Berlin"}},
            _EXCL,
        )

    assert len(calls) >= 1
    assert calls[0]["site_name"] == ["google", "zip_recruiter"]


def test_jobspy_sites_auto_derive_when_not_configured(monkeypatch):
    """When sites is absent, sources are derived from the region's ISO code."""
    calls = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        import pandas as pd

        return pd.DataFrame(
            columns=["title", "company", "job_url", "date_posted", "description", "site"]
        )

    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=fake_scrape_jobs))

    cfg = {
        "http": {
            "job_boards": {
                "jobspy": {
                    "enabled": True,
                    "results_per_query": 5,
                    "hours_old": 72,
                    "glassdoor_enabled": False,
                    "linkedin_enabled": False,
                    "linkedin_fetch_description": False,
                    # no "sites" key
                }
            }
        }
    }

    with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=cfg):
        fetch_jobspy_jobs(
            ["Software Engineer"],
            {"DE": {"country": "DE", "location": "Berlin"}},
            _EXCL,
        )

    # Auto-derive: google always + indeed for DE (has an Indeed mapping)
    assert "google" in calls[0]["site_name"]
    assert "indeed" in calls[0]["site_name"]
    assert "zip_recruiter" not in calls[0]["site_name"]


# ═══════════════════════════════════════════════════════════════════════════
# Regional sources — MyCareersFuture / EURES / JobBank / WTTJ / Glints /
#                   IrishJobs / GulfTalent / Naukrigulf / JobStreet
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


# ── MyCareersFuture ──────────────────────────────────────────────────────────

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


def test_mcf_success():
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
        jobs = fetch_mycareersfuture_jobs(["Product Manager"], _SG, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "MyCareersFuture"
    assert jobs[0]["company"] == "GovTech"
    assert "abc-123" in jobs[0]["url"]


def test_mcf_region_guard_skips_non_sg():
    with (
        patch(
            "job_hunter_core.sources.mycareersfuture_source.load_api_config",
            return_value=_EMPTY_CFG,
        ),
        patch("job_hunter_core.sources.mycareersfuture_source.requests.get") as mock_get,
    ):
        fetch_mycareersfuture_jobs(["Product Manager"], _DE, _CONFIG)
    mock_get.assert_not_called()


def test_mcf_http_error():
    with (
        patch(
            "job_hunter_core.sources.mycareersfuture_source.load_api_config",
            return_value=_EMPTY_CFG,
        ),
        patch(
            "job_hunter_core.sources.mycareersfuture_source.requests.get",
            side_effect=requests.exceptions.HTTPError("503"),
        ),
    ):
        assert fetch_mycareersfuture_jobs(["Product Manager"], _SG, _CONFIG) == []


def test_mcf_disabled():
    with (
        patch(
            "job_hunter_core.sources.mycareersfuture_source.load_api_config",
            return_value=_disabled("mycareersfuture"),
        ),
        patch("job_hunter_core.sources.mycareersfuture_source.requests.get") as mock_get,
    ):
        fetch_mycareersfuture_jobs(["Product Manager"], _SG, _CONFIG)
    mock_get.assert_not_called()


# ── EURES ────────────────────────────────────────────────────────────────────

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


def test_eures_success():
    with (
        patch("job_hunter_core.sources.eures_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.eures_source.requests.post",
            return_value=_mock_post(_EURES_RESPONSE),
        ),
    ):
        jobs = fetch_eures_jobs(["Product Manager"], _NL, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "EURES"
    assert jobs[0]["company"] == "EuroCorp"


def test_eures_region_guard_skips_non_eu():
    with (
        patch("job_hunter_core.sources.eures_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.eures_source.requests.post") as mock_post,
    ):
        fetch_eures_jobs(["Product Manager"], _SG, _CONFIG)
    mock_post.assert_not_called()


def test_eures_http_error():
    with (
        patch("job_hunter_core.sources.eures_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.eures_source.requests.post",
            side_effect=requests.exceptions.HTTPError("500"),
        ),
    ):
        assert fetch_eures_jobs(["Product Manager"], _NL, _CONFIG) == []


def test_eures_disabled():
    with (
        patch(
            "job_hunter_core.sources.eures_source.load_api_config", return_value=_disabled("eures")
        ),
        patch("job_hunter_core.sources.eures_source.requests.post") as mock_post,
    ):
        fetch_eures_jobs(["Product Manager"], _NL, _CONFIG)
    mock_post.assert_not_called()


# ── Job Bank Canada ──────────────────────────────────────────────────────────

_JB_HTML = """<html><body>
<article class="resultcount">
  <h3><a href="/job-posting/12345">Product Manager</a></h3>
  <span class="business-title">CanadaCorp</span>
  <span class="location">Toronto, ON</span>
  <span class="date">2026-06-01</span>
</article></body></html>"""


def test_jobbank_success():
    with (
        patch("job_hunter_core.sources.jobbank_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.jobbank_source.requests.get", return_value=_mock_html(_JB_HTML)
        ),
    ):
        jobs = fetch_jobbank_jobs(["Product Manager"], _CA, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "JobBank Canada"
    assert jobs[0]["title"] == "Product Manager"


def test_jobbank_region_guard_skips_non_ca():
    with (
        patch("job_hunter_core.sources.jobbank_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.jobbank_source.requests.get") as mock_get,
    ):
        fetch_jobbank_jobs(["Product Manager"], _AE, _CONFIG)
    mock_get.assert_not_called()


def test_jobbank_http_error():
    with (
        patch("job_hunter_core.sources.jobbank_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.jobbank_source.requests.get",
            side_effect=requests.exceptions.HTTPError("404"),
        ),
    ):
        assert fetch_jobbank_jobs(["Product Manager"], _CA, _CONFIG) == []


def test_jobbank_disabled():
    with (
        patch(
            "job_hunter_core.sources.jobbank_source.load_api_config",
            return_value=_disabled("jobbank"),
        ),
        patch("job_hunter_core.sources.jobbank_source.requests.get") as mock_get,
    ):
        fetch_jobbank_jobs(["Product Manager"], _CA, _CONFIG)
    mock_get.assert_not_called()


# ── Welcome to the Jungle ─────────────────────────────────────────────────────

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


def test_wttj_success():
    with (
        patch("job_hunter_core.sources.wttj_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.wttj_source.requests.get",
            return_value=_mock_get(_WTTJ_RESPONSE),
        ),
    ):
        jobs = fetch_wttj_jobs(["Product Manager"], _FR, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "Welcome to the Jungle"
    assert "startupfr" in jobs[0]["url"]


def test_wttj_http_error():
    with (
        patch("job_hunter_core.sources.wttj_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.wttj_source.requests.get",
            side_effect=requests.exceptions.ConnectionError("timeout"),
        ),
    ):
        assert fetch_wttj_jobs(["Product Manager"], _FR, _CONFIG) == []


def test_wttj_disabled():
    with (
        patch(
            "job_hunter_core.sources.wttj_source.load_api_config", return_value=_disabled("wttj")
        ),
        patch("job_hunter_core.sources.wttj_source.requests.get") as mock_get,
    ):
        fetch_wttj_jobs(["Product Manager"], _FR, _CONFIG)
    mock_get.assert_not_called()


def test_wttj_deduplicates_across_regions():
    two_regions = {
        "fr": {"country": "FR", "location": "Paris"},
        "remote": {"country": "FR", "location": "Remote"},
    }
    with (
        patch("job_hunter_core.sources.wttj_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.wttj_source.requests.get",
            return_value=_mock_get(_WTTJ_RESPONSE),
        ),
    ):
        jobs = fetch_wttj_jobs(["Product Manager"], two_regions, _CONFIG)
    urls = [j["url"] for j in jobs]
    assert len(urls) == len(set(urls))


# ── Glints ───────────────────────────────────────────────────────────────────

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


def test_glints_success():
    with (
        patch("job_hunter_core.sources.glints_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.glints_source.requests.get",
            return_value=_mock_get(_GLINTS_RESPONSE),
        ),
    ):
        jobs = fetch_glints_jobs(["Product Manager"], _SG, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "Glints"
    assert "gl-101" in jobs[0]["url"]


def test_glints_region_guard_skips_non_sea():
    with (
        patch("job_hunter_core.sources.glints_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.glints_source.requests.get") as mock_get,
    ):
        fetch_glints_jobs(["Product Manager"], _GB, _CONFIG)
    mock_get.assert_not_called()


def test_glints_http_error():
    with (
        patch("job_hunter_core.sources.glints_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.glints_source.requests.get",
            side_effect=requests.exceptions.Timeout("timeout"),
        ),
    ):
        assert fetch_glints_jobs(["Product Manager"], _SG, _CONFIG) == []


def test_glints_disabled():
    with (
        patch(
            "job_hunter_core.sources.glints_source.load_api_config",
            return_value=_disabled("glints"),
        ),
        patch("job_hunter_core.sources.glints_source.requests.get") as mock_get,
    ):
        fetch_glints_jobs(["Product Manager"], _SG, _CONFIG)
    mock_get.assert_not_called()


# ── IrishJobs ────────────────────────────────────────────────────────────────

_IJ_HTML = """<html><body>
<div class="jobadvert">
  <h2><a class="jobTitle" href="/jobs/123">Product Manager</a></h2>
  <span class="company">IrishTech</span>
  <span class="location">Dublin</span>
</div></body></html>"""


def test_irishjobs_success():
    with (
        patch("job_hunter_core.sources.irishjobs_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.irishjobs_source.requests.get",
            return_value=_mock_html(_IJ_HTML),
        ),
    ):
        jobs = fetch_irishjobs_jobs(["Product Manager"], _IE, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "IrishJobs"
    assert jobs[0]["title"] == "Product Manager"


def test_irishjobs_region_guard_skips_non_ie():
    with (
        patch("job_hunter_core.sources.irishjobs_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.irishjobs_source.requests.get") as mock_get,
    ):
        fetch_irishjobs_jobs(["Product Manager"], _CA, _CONFIG)
    mock_get.assert_not_called()


def test_irishjobs_http_error():
    with (
        patch("job_hunter_core.sources.irishjobs_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.irishjobs_source.requests.get",
            side_effect=requests.exceptions.HTTPError("503"),
        ),
    ):
        assert fetch_irishjobs_jobs(["Product Manager"], _IE, _CONFIG) == []


def test_irishjobs_disabled():
    with (
        patch(
            "job_hunter_core.sources.irishjobs_source.load_api_config",
            return_value=_disabled("irishjobs"),
        ),
        patch("job_hunter_core.sources.irishjobs_source.requests.get") as mock_get,
    ):
        fetch_irishjobs_jobs(["Product Manager"], _IE, _CONFIG)
    mock_get.assert_not_called()


# ── GulfTalent ───────────────────────────────────────────────────────────────

_GT_HTML = """<html><body>
<div class="job-listing">
  <h2><a class="job-title" href="/jobs/456">Product Manager</a></h2>
  <span class="company-name">GulfCorp</span>
  <span class="location">Dubai, UAE</span>
</div></body></html>"""


def test_gulftalent_success():
    with (
        patch("job_hunter_core.sources.gulftalent_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.gulftalent_source.requests.get",
            return_value=_mock_html(_GT_HTML),
        ),
    ):
        jobs = fetch_gulftalent_jobs(["Product Manager"], _AE, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "GulfTalent"


def test_gulftalent_region_guard_skips_non_gulf():
    with (
        patch("job_hunter_core.sources.gulftalent_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.gulftalent_source.requests.get") as mock_get,
    ):
        fetch_gulftalent_jobs(["Product Manager"], _FR, _CONFIG)
    mock_get.assert_not_called()


def test_gulftalent_playwright_fallback_on_blocked():
    with (
        patch("job_hunter_core.sources.gulftalent_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.gulftalent_source.requests.get",
            side_effect=requests.exceptions.ConnectionError("blocked"),
        ),
        patch(
            "job_hunter_core.sources.gulftalent_source._fetch_with_playwright", return_value=""
        ) as mock_pw,
    ):
        jobs = fetch_gulftalent_jobs(["Product Manager"], _AE, _CONFIG)
    assert jobs == []
    mock_pw.assert_called_once()


def test_gulftalent_disabled():
    with (
        patch(
            "job_hunter_core.sources.gulftalent_source.load_api_config",
            return_value=_disabled("gulftalent"),
        ),
        patch("job_hunter_core.sources.gulftalent_source.requests.get") as mock_get,
    ):
        fetch_gulftalent_jobs(["Product Manager"], _AE, _CONFIG)
    mock_get.assert_not_called()


# ── Naukrigulf ───────────────────────────────────────────────────────────────

_NG_HTML = """<html><body>
<div class="jobTuple">
  <h3><a class="designation" href="/pm-jobs-in-uae-nj12345">Product Manager</a></h3>
  <span class="comp-name">NaukriCorp</span>
  <span class="loc">Dubai</span>
</div></body></html>"""


def test_naukrigulf_success():
    with (
        patch("job_hunter_core.sources.naukrigulf_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.naukrigulf_source.requests.get",
            return_value=_mock_html(_NG_HTML),
        ),
    ):
        jobs = fetch_naukrigulf_jobs(["Product Manager"], _SA, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "Naukrigulf"


def test_naukrigulf_region_guard_skips_non_gulf():
    with (
        patch("job_hunter_core.sources.naukrigulf_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.naukrigulf_source.requests.get") as mock_get,
    ):
        fetch_naukrigulf_jobs(["Product Manager"], _IE, _CONFIG)
    mock_get.assert_not_called()


def test_naukrigulf_playwright_fallback_on_blocked():
    with (
        patch("job_hunter_core.sources.naukrigulf_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.naukrigulf_source.requests.get",
            side_effect=requests.exceptions.ConnectionError("blocked"),
        ),
        patch(
            "job_hunter_core.sources.naukrigulf_source._fetch_with_playwright", return_value=""
        ) as mock_pw,
    ):
        jobs = fetch_naukrigulf_jobs(["Product Manager"], _SA, _CONFIG)
    assert jobs == []
    mock_pw.assert_called_once()


def test_naukrigulf_disabled():
    with (
        patch(
            "job_hunter_core.sources.naukrigulf_source.load_api_config",
            return_value=_disabled("naukrigulf"),
        ),
        patch("job_hunter_core.sources.naukrigulf_source.requests.get") as mock_get,
    ):
        fetch_naukrigulf_jobs(["Product Manager"], _SA, _CONFIG)
    mock_get.assert_not_called()


# ── JobStreet ────────────────────────────────────────────────────────────────

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


def test_jobstreet_success():
    with (
        patch("job_hunter_core.sources.jobstreet_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.jobstreet_source.requests.get",
            return_value=_mock_get(_JS_RESPONSE),
        ),
    ):
        jobs = fetch_jobstreet_jobs(["Product Manager"], _MY, _CONFIG)
    assert len(jobs) == 1
    assert jobs[0]["source"] == "JobStreet"
    assert "js-9001" in jobs[0]["url"]


def test_jobstreet_region_guard_skips_non_sea():
    with (
        patch("job_hunter_core.sources.jobstreet_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.jobstreet_source.requests.get") as mock_get,
    ):
        fetch_jobstreet_jobs(["Product Manager"], _DE, _CONFIG)
    mock_get.assert_not_called()


def test_jobstreet_http_error():
    with (
        patch("job_hunter_core.sources.jobstreet_source.load_api_config", return_value=_EMPTY_CFG),
        patch(
            "job_hunter_core.sources.jobstreet_source.requests.get",
            side_effect=requests.exceptions.HTTPError("500"),
        ),
    ):
        assert fetch_jobstreet_jobs(["Product Manager"], _MY, _CONFIG) == []


def test_jobstreet_disabled():
    with (
        patch(
            "job_hunter_core.sources.jobstreet_source.load_api_config",
            return_value=_disabled("jobstreet"),
        ),
        patch("job_hunter_core.sources.jobstreet_source.requests.get") as mock_get,
    ):
        fetch_jobstreet_jobs(["Product Manager"], _MY, _CONFIG)
    mock_get.assert_not_called()


def test_jobstreet_403_triggers_playwright_path():
    resp_403 = MagicMock()
    resp_403.status_code = 403
    resp_403.raise_for_status = MagicMock()
    resp_403.json.return_value = {}
    with (
        patch("job_hunter_core.sources.jobstreet_source.load_api_config", return_value=_EMPTY_CFG),
        patch("job_hunter_core.sources.jobstreet_source.requests.get", return_value=resp_403),
        patch(
            "job_hunter_core.sources.jobstreet_source._fetch_page_playwright", return_value=[]
        ) as mock_pw,
    ):
        jobs = fetch_jobstreet_jobs(["Product Manager"], _MY, _CONFIG)
    assert jobs == []
    mock_pw.assert_called_once()
