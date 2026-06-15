"""Tests for sources/scraper — all HTTP calls are mocked.

The scraper is source-first: every configured title is searched across every
enabled source for every enabled region. There is no company list or company loop.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from job_hunter_core.core.utils import title_matches
from job_hunter_core.sources import scraper


@pytest.fixture(autouse=True)
def _no_preflight(monkeypatch):
    """Prevent run-start preflight from making live HTTP calls in scraper tests."""
    monkeypatch.setattr(
        "job_hunter_core.sources.scraper.probe_search_providers",
        lambda: set(),
    )
    monkeypatch.setattr(
        "job_hunter_core.sources.scraper.probe_job_sources",
        lambda *_args: {},
    )


CONFIG = {
    "exclusion_rules": {
        "senior_flags": ["director", "vp ", "head of product"],
        "excluded_industries": ["banking", "casino"],
        "excluded_languages": ["german"],
        "language_indicators": {
            "german": ["wir suchen", "vollzeit", "m/w/d"],
        },
        "stale_indicators": ["no longer available", "position has been filled"],
    },
    "global_search": {
        "job_titles": ["Product Manager", "Product Owner"],
    },
    "regions": {
        "berlin": {
            "enabled": True,
            "country": "DE",
            "search_lang": "en",
            "location": "Berlin",
        }
    },
    "llm_job_search": {
        "enabled": False,
    },
}


_EXTERNAL_PATCHES = [
    ("job_hunter_core.sources.scraper.discover_ats_jobs_by_search", []),
    ("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", []),
    ("job_hunter_core.sources.jobspy_source.JobSpySource.fetch", []),
    ("job_hunter_core.sources.himalayas_source.HimalayasSource.fetch", []),
    ("job_hunter_core.sources.remotive_source.RemotiveSource.fetch", []),
    ("job_hunter_core.sources.the_muse_source.TheMuseSource.fetch", []),
    ("job_hunter_core.sources.jobicy_source.JobicySource.fetch", []),
    ("job_hunter_core.sources.remoteok_source.RemoteOKSource.fetch", []),
    ("job_hunter_core.sources.weworkremotely_source.WeWorkRemotelySource.fetch", []),
    ("job_hunter_core.sources.mycareersfuture_source.MyCareersFutureSource.fetch", []),
    ("job_hunter_core.sources.jobbank_source.JobBankSource.fetch", []),
    ("job_hunter_core.sources.glints_source.GlintsSource.fetch", []),
    ("job_hunter_core.sources.gulftalent_source.GulfTalentSource.fetch", []),
    ("job_hunter_core.sources.jobstreet_source.JobStreetSource.fetch", []),
    ("job_hunter_core.sources.jooble_source.JoobleSource.fetch", []),
    ("job_hunter_core.sources.arbeitsagentur_source.ArbeitsagenturSource.fetch", []),
    ("job_hunter_core.sources.job_boards.ArbeitnowSource.fetch", []),
    ("job_hunter_core.sources.job_boards.JSearchSource.fetch", []),
    ("job_hunter_core.sources.adzuna_source.AdzunaSource.fetch", []),
    ("job_hunter_core.sources.reed_source.ReedSource.fetch", []),
    ("job_hunter_core.sources.scraper.load_cached_candidate_urls", set()),
    ("job_hunter_core.sources.scraper.save_cached_candidate_urls", None),
]


@pytest.fixture(autouse=True)
def _disable_external_scrape_paths():
    """Silence all external I/O so only the paths under test are exercised."""
    with ExitStack() as stack:
        for target, return_val in _EXTERNAL_PATCHES:
            if return_val is None:
                stack.enter_context(patch(target))
            else:
                stack.enter_context(patch(target, return_value=return_val))
        yield


def _make_posting(url, title="Product Manager", company="TestCo", snippet="PM role"):
    m = MagicMock()
    m.to_dict.return_value = {
        "url": url,
        "title": title,
        "company": company,
        "snippet": snippet,
        "posted": "",
        "source": "test",
    }
    return m


def _mock_http(results, status=200):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"web": {"results": results}}
    return resp


# ── is_valid_job_url() ───────────────────────────────────────────────────────


def test_valid_job_url_accepts_deep_path():
    assert scraper.is_valid_job_url("https://boards.greenhouse.io/deliveryhero/jobs/12345") is True


def test_valid_job_url_accepts_lever_slug():
    assert (
        scraper.is_valid_job_url("https://jobs.lever.co/getyourguide/product-manager-berlin")
        is True
    )


def test_valid_job_url_rejects_domain_root():
    assert scraper.is_valid_job_url("https://jobs.testco.com") is False


def test_valid_job_url_rejects_root_slash():
    assert scraper.is_valid_job_url("https://jobs.testco.com/") is False


def test_valid_job_url_rejects_listing_page_careers():
    assert scraper.is_valid_job_url("https://company.com/careers") is False


def test_valid_job_url_rejects_listing_page_jobs():
    assert scraper.is_valid_job_url("https://company.com/jobs") is False


def test_valid_job_url_rejects_single_segment_ats():
    assert scraper.is_valid_job_url("https://boards.greenhouse.io/deliveryhero") is False


def test_valid_job_url_accepts_two_segment_path():
    assert scraper.is_valid_job_url("https://jobs.testco.com/en/job/12345") is True


def test_excluded_url_patterns_are_configured():
    config = {
        "exclusion_rules": {
            "excluded_url_patterns": [r"linkedin\.com/jobs/search"],
        },
    }
    assert (
        scraper.is_excluded_url("https://www.linkedin.com/jobs/search?keywords=pm", config) is True
    )
    assert scraper.is_excluded_url("https://www.linkedin.com/jobs/view/123", config) is False


# ── is_stale_posting() ───────────────────────────────────────────────────────


def test_stale_posting_detects_no_longer_available():
    assert scraper.is_stale_posting("PM role", "This job is no longer available", CONFIG) is True


def test_stale_posting_detects_filled():
    assert scraper.is_stale_posting("PM role", "The position has been filled", CONFIG) is True


def test_stale_posting_passes_active_job():
    assert scraper.is_stale_posting("PM Berlin", "Join our growing team in Berlin", CONFIG) is False


# ── Language filtering ────────────────────────────────────────────────────────


def test_german_language_heuristic_rejects_adzuna_style_description():
    snippet = (
        "Mitte, Berlin - Deine Mission In dieser Position treibst du die strategische "
        "Weiterentwicklung unserer Cloud aktiv voran. An der Schnittstelle von User "
        "Experience, Tech und Business gestaltest du Produkte, die echten Mehrwert "
        "schaffen. Mit deinem Blick fuer das Ganze sorgst du fuer klare Priorisierung."
    )
    assert scraper.is_german("Product Manager:in", snippet, CONFIG) is True


def test_german_language_heuristic_allows_english_berlin_description():
    snippet = (
        "Berlin, Germany - You will own product discovery for a cloud platform, work "
        "with engineering and design, define priorities, and speak with customers to "
        "shape measurable outcomes for product teams."
    )
    assert scraper.is_german("Product Manager", snippet, CONFIG) is False


def test_german_language_filter_disabled_when_not_in_excluded_languages():
    config = {
        **CONFIG,
        "exclusion_rules": {
            **CONFIG["exclusion_rules"],
            "excluded_languages": [],
        },
    }
    snippet = (
        "Berlin, Deutschland - Deine kuenftigen Aufgaben umfassen Verantwortung "
        "fuer Aufbau, Struktur, Priorisierung und kontinuierliches Refinement des "
        "Product Backlogs sowie die Uebersetzung von Anforderungen in klare Aufgaben."
    )
    assert scraper.is_german("Product Owner", snippet, config) is False


def test_language_indicator_triggers_exclusion():
    snippet = "wir suchen einen Product Manager für unser Team"
    assert scraper.is_german("PM", snippet, CONFIG) is True


# ── brave_search() ───────────────────────────────────────────────────────────


def test_brave_search_returns_results():
    results = [{"url": "https://jobs.testco.com/en/pm", "title": "PM", "description": "role"}]
    with patch("job_hunter_core.sources.scraper.requests.get", return_value=_mock_http(results)):
        out = scraper.brave_search("query", {"country": "DE", "search_lang": "en"})
    assert len(out) == 1
    assert out[0]["url"] == "https://jobs.testco.com/en/pm"


def test_brave_search_returns_empty_on_no_results():
    with patch("job_hunter_core.sources.scraper.requests.get", return_value=_mock_http([])):
        out = scraper.brave_search("query", {"country": "DE"})
    assert out == []


def test_brave_search_raises_on_http_error():
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("HTTP 429")
    with patch("job_hunter_core.sources.scraper.requests.get", return_value=resp):
        with pytest.raises(Exception):  # noqa: B017
            scraper.brave_search("query", {"country": "DE"})


def test_brave_search_omits_unsupported_country_codes():
    results = [{"url": "https://jobs.example.com/en/pm", "title": "PM", "description": "role"}]
    with patch(
        "job_hunter_core.sources.scraper.requests.get", return_value=_mock_http(results)
    ) as mock_get:
        scraper.brave_search("query", {"country": "QA", "search_lang": "en"})

    call_params = mock_get.call_args[1]["params"]
    assert "country" not in call_params
    assert call_params["search_lang"] == "en"


# ── scrape() — source-first behavior ─────────────────────────────────────────


def test_scrape_returns_empty_when_no_job_titles():
    config = {**CONFIG, "global_search": {"job_titles": []}}
    with patch("job_hunter_core.sources.scraper.load_search_config", return_value=config):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_returns_empty_when_no_enabled_regions():
    config = {
        **CONFIG,
        "regions": {"berlin": {"enabled": False, "country": "DE", "location": "Berlin"}},
    }
    with patch("job_hunter_core.sources.scraper.load_search_config", return_value=config):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_runs_ats_discovery_and_accepts_results():
    discovery_job = {
        "title": "Product Manager",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discoveryco/12345678-1234-1234-1234-123456789abc",
        "posted": "",
        "snippet": "PM role at DiscoveryCo",
        "source": "SearXNG ATS discovery: lever",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.scraper.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
    ):
        jobs = scraper.scrape()
    assert len(jobs) == 1
    assert jobs[0]["company"] == "DiscoveryCo"


def test_scrape_deduplicates_same_url_across_sources():
    job = {
        "url": "https://jobs.testco.com/en/pm",
        "title": "Product Manager",
        "company": "TestCo",
        "snippet": "PM role",
        "posted": "",
        "source": "test",
    }
    posting = MagicMock()
    posting.to_dict.return_value = {**job}
    posting2 = MagicMock()
    posting2.to_dict.return_value = {**job, "source": "test2"}

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.jobspy_source.JobSpySource.fetch", return_value=[posting]),
        patch(
            "job_hunter_core.sources.himalayas_source.HimalayasSource.fetch",
            return_value=[posting2],
        ),
    ):
        jobs = scraper.scrape()

    urls = [j["url"] for j in jobs]
    assert len(urls) == len(set(urls))
    assert len(jobs) == 1


def test_scrape_deduplicates_canonical_urls():
    job1 = {
        "url": "https://www.jobs.testco.com/en/pm?utm_source=x&a=1",
        "title": "Product Manager",
        "company": "TestCo",
        "snippet": "PM role",
        "posted": "",
        "source": "source1",
    }
    job2 = {
        "url": "https://jobs.testco.com/en/pm?a=1",
        "title": "Product Manager duplicate",
        "company": "TestCo",
        "snippet": "PM role",
        "posted": "",
        "source": "source2",
    }
    p1, p2 = MagicMock(), MagicMock()
    p1.to_dict.return_value = job1
    p2.to_dict.return_value = job2

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.jobspy_source.JobSpySource.fetch", return_value=[p1]),
        patch("job_hunter_core.sources.himalayas_source.HimalayasSource.fetch", return_value=[p2]),
    ):
        jobs = scraper.scrape()

    assert len(jobs) == 1


def test_scrape_applies_seniority_filter():
    senior_posting = _make_posting(
        "https://boards.greenhouse.io/testco/jobs/senior",
        title="Director of Product",
        snippet="senior leadership role",
    )
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.jobspy_source.JobSpySource.fetch",
            return_value=[senior_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_applies_industry_filter():
    banking_posting = _make_posting(
        "https://boards.greenhouse.io/testco/jobs/bank",
        snippet="banking platform role",
    )
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.jobspy_source.JobSpySource.fetch",
            return_value=[banking_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_applies_stale_indicator_filter():
    stale_discovery = {
        "title": "Product Manager",
        "company": "TestCo",
        "url": "https://jobs.lever.co/testco/12345",
        "snippet": "no longer available",
        "posted": "",
        "source": "ats",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.scraper.discover_ats_jobs_by_search",
            return_value=[stale_discovery],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_applies_german_language_filter_via_language_indicators():
    german_posting = _make_posting(
        "https://jobs.testco.com/en/pm",
        title="PM m/w/d",
        snippet="vollzeit",
    )
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.jobspy_source.JobSpySource.fetch",
            return_value=[german_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_skips_adzuna_german_descriptions():
    adzuna_job = {
        "title": "Product Owner",
        "company": "AdzunaCo",
        "url": "https://www.adzuna.de/details/123",
        "posted": "2026-05-26",
        "snippet": (
            "Berlin, Deutschland - Deine kuenftigen Aufgaben umfassen Verantwortung "
            "fuer Aufbau, Struktur, Priorisierung und kontinuierliches Refinement des "
            "Product Backlogs sowie die Uebersetzung von Anforderungen in klare Aufgaben."
        ),
        "source": "Adzuna",
    }
    adzuna_posting = MagicMock()
    adzuna_posting.to_dict.return_value = adzuna_job

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.adzuna_source.AdzunaSource.fetch",
            return_value=[adzuna_posting],
        ),
    ):
        jobs = scraper.scrape()

    assert jobs == []


def test_scrape_skips_cached_discovery_candidates():
    discovery_job = {
        "title": "Product Owner",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discovery/12345678-1234-1234-1234-123456789abc",
        "posted": "",
        "snippet": "Discovery role",
        "source": "SearXNG ATS discovery: lever",
    }

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.scraper.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
        patch(
            "job_hunter_core.sources.scraper.load_cached_candidate_urls",
            return_value={scraper.canonicalize_url(discovery_job["url"])},
        ),
        patch("job_hunter_core.sources.scraper.save_cached_candidate_urls") as save_cache,
    ):
        jobs = scraper.scrape()

    assert jobs == []
    save_cache.assert_not_called()


def test_scrape_continues_after_source_failure():
    good_posting = _make_posting("https://boards.greenhouse.io/testco/jobs/12345")
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.jobspy_source.JobSpySource.fetch",
            side_effect=RuntimeError("jobspy boom"),
        ),
        patch(
            "job_hunter_core.sources.himalayas_source.HimalayasSource.fetch",
            return_value=[good_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert len(jobs) == 1


# ── scrape() — LLM search gating ─────────────────────────────────────────────


def test_scrape_runs_llm_search_when_enabled_and_below_threshold():
    ai_job = {
        "title": "Product Owner",
        "company": "LinkedCo",
        "url": "https://www.linkedin.com/jobs/view/123456",
        "posted": "",
        "snippet": "Product backlog role",
        "source": "AI web search: linkedin",
    }
    config = {
        **CONFIG,
        "llm_job_search": {"enabled": True, "trigger_threshold": 5},
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=config),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", return_value=[ai_job]),
    ):
        jobs = scraper.scrape()
    assert jobs == [ai_job]


def test_scrape_skips_llm_search_when_disabled():
    ai_mock = MagicMock()
    config = {**CONFIG, "llm_job_search": {"enabled": False}}
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=config),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", ai_mock),
    ):
        scraper.scrape()
    ai_mock.assert_not_called()


def test_scrape_skips_llm_search_when_results_meet_threshold():
    good_posting = _make_posting("https://boards.greenhouse.io/testco/jobs/12345")
    config = {
        **CONFIG,
        "llm_job_search": {"enabled": True, "trigger_threshold": 1},
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=config),
        patch(
            "job_hunter_core.sources.himalayas_source.HimalayasSource.fetch",
            return_value=[good_posting],
        ),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs") as ai_mock,
    ):
        jobs = scraper.scrape()
    assert any(j["url"] == "https://boards.greenhouse.io/testco/jobs/12345" for j in jobs)
    ai_mock.assert_not_called()


# ── title_matches() ──────────────────────────────────────────────────────────


def test_title_matches_rejects_irrelevant_product_titles():
    filters = ["Product Manager", "Product Owner"]
    assert title_matches("Senior Product Manager", filters) is True
    assert title_matches("Technical Product Owner", filters) is True
    assert title_matches("Product Engineer", filters) is False
    assert title_matches("Working Student Product Management", filters) is False


def test_title_exclusions_are_caller_configured():
    filters = ["Product Manager"]
    assert title_matches("Product Manager Engineer", filters) is True
    assert title_matches("Product Manager Engineer", filters, ["engineer"]) is False


# ── ScrapeStats diagnostics ───────────────────────────────────────────────────


def test_scrape_stats_records_accepted_and_skipped():
    stats = scraper.ScrapeStats()
    stats.record("ats_api", attempted=3, returned=2, accepted=1, skipped=1)
    s = stats.source("ats_api")
    assert s.attempted == 3
    assert s.returned == 2
    assert s.accepted == 1
    assert s.skipped == 1


def test_scrape_stats_log_summary_does_not_raise(caplog):
    import logging

    stats = scraper.ScrapeStats()
    stats.record("test_source", attempted=1, returned=0, failed=1)
    with caplog.at_level(logging.INFO):
        stats.log_summary()
    assert any("test_source" in r.message for r in caplog.records)


def test_scrape_stats_to_dict_matches_recorded_values():
    stats = scraper.ScrapeStats()
    stats.record("jobspy", attempted=5, returned=3, accepted=2, skipped=1)
    d = stats.to_dict()
    assert d["jobspy"]["attempted"] == 5
    assert d["jobspy"]["returned"] == 3
    assert d["jobspy"]["accepted"] == 2
    assert d["jobspy"]["skipped"] == 1


def test_scrape_diagnostics_ats_discovery_success_source_failure():
    discovery_job = {
        "title": "Product Manager",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discoveryco/abc123",
        "posted": "",
        "snippet": "PM role",
        "source": "SearXNG ATS discovery: lever",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter_core.sources.scraper.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
        patch(
            "job_hunter_core.sources.jobspy_source.JobSpySource.fetch",
            side_effect=RuntimeError("jobspy boom"),
        ),
    ):
        jobs = scraper.scrape()

    assert any(j["url"] == discovery_job["url"] for j in jobs)
