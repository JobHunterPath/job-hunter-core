"""Tests for new job source modules — all HTTP calls are mocked."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from job_hunter_core.sources.adzuna_source import fetch_adzuna_jobs
from job_hunter_core.sources.jobicy_source import fetch_jobicy_jobs
from job_hunter_core.sources.jobspy_source import fetch_jobspy_jobs
from job_hunter_core.sources.jooble_source import fetch_jooble_jobs
from job_hunter_core.sources.reed_source import fetch_reed_jobs
from job_hunter_core.sources.remoteok_source import fetch_remoteok_jobs
from job_hunter_core.sources.weworkremotely_source import fetch_weworkremotely_jobs

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
