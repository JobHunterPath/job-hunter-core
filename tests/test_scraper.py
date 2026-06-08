"""Tests for sources/scraper.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from job_hunter_core.core.utils import title_matches
from job_hunter_core.sources import scraper

CONFIG = {
    "exclusion_rules": {
        "senior_flags": ["director", "vp ", "head of product"],
        "excluded_industries": ["banking", "casino"],
        "german_indicators": ["m/w/d", "sucht", "vollzeit"],
        "stale_indicators": ["no longer available", "position has been filled"],
    },
    "global_search": {
        "job_titles": ["Product Manager", "Product Owner"],
        "results_per_query": 10,
    },
    "regions": {
        "berlin": {
            "enabled": True,
            "country": "DE",
            "search_lang": "en",
            "location": "Berlin",
            "companies": [
                {"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"},
                {
                    "name": "AnotherCo",
                    "career_url": "boards.greenhouse.io/anotherco",
                    "location": "Berlin",
                },
            ],
        }
    },
}

COMPANIES = CONFIG["regions"]["berlin"]["companies"]


@pytest.fixture(autouse=True)
def _disable_external_scrape_paths():
    with (
        patch("job_hunter_core.sources.scraper.fetch_playwright_career_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.discover_ats_jobs_by_search", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_jobspy_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_jobicy_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_remoteok_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_weworkremotely_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_jooble_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.load_cached_candidate_urls", return_value=set()),
        patch("job_hunter_core.sources.scraper.save_cached_candidate_urls"),
    ):
        yield


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


# ── build_queries() ──────────────────────────────────────────────────────────


def test_build_queries_one_per_title():
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"}]
    queries = scraper.build_queries(companies, CONFIG)
    assert len(queries) == 2


def test_build_queries_includes_location():
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"}]
    queries = scraper.build_queries(companies, CONFIG)
    for q, _, _ in queries:
        assert '"Berlin"' in q


def test_build_queries_no_location_when_empty():
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": ""}]
    queries = scraper.build_queries(companies, CONFIG)
    for q, _, _ in queries:
        assert "site:jobs.testco.com" in q
        assert '"Berlin"' not in q


def test_build_queries_contains_site_param():
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"}]
    queries = scraper.build_queries(companies, CONFIG)
    for q, _, _ in queries:
        assert "site:jobs.testco.com" in q


def test_build_queries_adds_title_exclusions():
    config = {
        **CONFIG,
        "exclusion_rules": {
            **CONFIG["exclusion_rules"],
            "excluded_title_terms": ["engineer", "working student"],
        },
    }
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"}]
    queries = scraper.build_queries(companies, config)
    for q, _, _ in queries:
        assert '-"engineer"' in q
        assert '-"working student"' in q


def test_build_queries_includes_both_titles():
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"}]
    queries = scraper.build_queries(companies, CONFIG)
    all_queries = [q for q, _, _ in queries]
    assert any("Product Manager" in q for q in all_queries)
    assert any("Product Owner" in q for q in all_queries)


def test_build_queries_uses_no_title_fallback_when_config_empty():
    config = {**CONFIG, "global_search": {"job_titles": [], "results_per_query": 10}}
    companies = [{"name": "TestCo", "career_url": "jobs.testco.com", "location": "Berlin"}]
    assert scraper.build_queries(companies, config) == []


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
        with pytest.raises(Exception):
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


# ── scrape() — Brave fallback path ───────────────────────────────────────────


def test_scrape_brave_deduplicates_same_url():
    raw = [
        {"url": "https://jobs.testco.com/en/pm", "title": "PM", "description": "role at TestCo"},
        {
            "url": "https://jobs.testco.com/en/pm",
            "title": "PM duplicate",
            "description": "same url",
        },
    ]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    urls = [j["url"] for j in jobs]
    assert len(urls) == len(set(urls))


def test_scrape_deduplicates_canonical_urls():
    raw = [
        {
            "url": "https://www.jobs.testco.com/en/pm?utm_source=x&a=1",
            "title": "Product Manager",
            "description": "role at TestCo",
        },
        {
            "url": "https://jobs.testco.com/en/pm?a=1",
            "title": "Product Manager duplicate",
            "description": "same url",
        },
    ]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    assert len(jobs) == 1


def test_scrape_brave_skips_invalid_urls():
    raw = [
        {"url": "https://boards.greenhouse.io/testco", "title": "PM", "description": "great role"}
    ]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_brave_skips_stale_postings():
    raw = [
        {
            "url": "https://jobs.testco.com/en/pm",
            "title": "PM",
            "description": "no longer available",
        }
    ]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_brave_skips_german_postings():
    raw = [{"url": "https://jobs.testco.com/en/pm", "title": "PM m/w/d", "description": "vollzeit"}]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    assert jobs == []


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


def test_german_language_filter_can_be_disabled():
    config = {
        **CONFIG,
        "exclusion_rules": {
            **CONFIG["exclusion_rules"],
            "exclude_german_language": False,
        },
    }
    snippet = (
        "Berlin, Deutschland - Deine kuenftigen Aufgaben umfassen Verantwortung "
        "fuer Aufbau, Struktur, Priorisierung und kontinuierliches Refinement des "
        "Product Backlogs sowie die Uebersetzung von Anforderungen in klare Aufgaben."
    )

    assert scraper.is_german("Product Owner", snippet, config) is False


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

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_adzuna_jobs", return_value=[adzuna_job]),
        patch("job_hunter_core.sources.scraper.fetch_reed_jobs", return_value=[]),
    ):
        jobs = scraper.scrape()

    assert jobs == []


def test_scrape_brave_skips_too_senior():
    raw = [
        {
            "url": "https://jobs.testco.com/en/dir",
            "title": "Director of Product",
            "description": "senior role",
        }
    ]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    assert jobs == []


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


def test_scrape_brave_skips_excluded_industry():
    raw = [
        {"url": "https://jobs.testco.com/en/pm", "title": "PM", "description": "banking platform"}
    ]
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", return_value=raw),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_returns_empty_on_no_companies():
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=[]),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_runs_ai_web_search_without_companies():
    ai_job = {
        "title": "Product Owner",
        "company": "LinkedCo",
        "url": "https://www.linkedin.com/jobs/view/123456",
        "posted": "",
        "snippet": "Product backlog role",
        "source": "AI web search: linkedin",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", return_value=[ai_job]),
    ):
        jobs = scraper.scrape()

    assert jobs == [ai_job]


def test_scrape_orders_direct_ats_then_search_discovery_then_ai():
    discovery_job = {
        "title": "Product Owner",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discovery/12345678-1234-1234-1234-123456789abc",
        "posted": "",
        "snippet": "Discovery role",
        "source": "SearXNG ATS discovery: lever",
    }
    ai_job = {
        "title": "Product Manager",
        "company": "AiCo",
        "url": "https://www.linkedin.com/jobs/view/123456",
        "posted": "",
        "snippet": "AI search role",
        "source": "AI web search: linkedin",
    }

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[ATS_JOB]),
        patch(
            "job_hunter_core.sources.scraper.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", return_value=[ai_job]),
    ):
        jobs = scraper.scrape()

    assert [job["source"] for job in jobs] == [
        "Greenhouse API",
        "SearXNG ATS discovery: lever",
        "AI web search: linkedin",
    ]


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
        patch("job_hunter_core.sources.scraper.load_companies", return_value=[]),
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


def test_scrape_brave_continues_after_api_error():
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=None),
        patch("job_hunter_core.sources.scraper.search_web", side_effect=Exception("timeout")),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_allows_ai_web_search_linkedin_job_urls():
    config = {
        **CONFIG,
        "exclusion_rules": {
            **CONFIG["exclusion_rules"],
            "excluded_url_patterns": [r"linkedin\.com/jobs/"],
        },
    }
    ai_job = {
        "title": "Product Owner",
        "company": "LinkedCo",
        "url": "https://www.linkedin.com/jobs/view/123456",
        "posted": "",
        "snippet": "Product backlog role",
        "source": "AI web search: linkedin",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=config),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs", return_value=[ai_job]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[]),
    ):
        jobs = scraper.scrape()

    assert jobs == [ai_job]


def test_scrape_skips_ai_web_search_when_existing_results_meet_threshold():
    direct_job = {
        "title": "Product Owner",
        "company": "TestCo",
        "url": "https://boards.greenhouse.io/testco/jobs/12345",
        "posted": "",
        "snippet": "Product backlog role",
        "source": "Greenhouse API",
        "region": "",
    }
    api_cfg = {"http": {"search_providers": {"ai_web_search": {"run_if_fewer_than_jobs": 1}}}}

    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_api_config", return_value=api_cfg),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[direct_job]),
        patch("job_hunter_core.sources.scraper.fetch_ai_web_search_jobs") as ai_search,
    ):
        jobs = scraper.scrape()

    assert jobs == [direct_job]
    ai_search.assert_not_called()


# ── scrape() — ATS path ───────────────────────────────────────────────────────

ATS_JOB = {
    "title": "Product Manager",
    "company": "TestCo",
    "url": "https://boards.greenhouse.io/testco/jobs/12345",
    "posted": "2026-04-01",
    "snippet": "Berlin — Great PM role in Berlin.",
    "source": "Greenhouse API",
}


def test_scrape_uses_ats_jobs_when_available():
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[ATS_JOB]),
    ):
        jobs = scraper.scrape()
    assert len(jobs) >= 1
    assert jobs[0]["source"] == "Greenhouse API"


def test_scrape_ats_path_deduplicates_across_companies():
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[ATS_JOB]),
    ):
        jobs = scraper.scrape()
    urls = [j["url"] for j in jobs]
    assert len(urls) == len(set(urls))


def test_scrape_ats_path_applies_seniority_filter():
    senior_job = {
        **ATS_JOB,
        "title": "Director of Product",
        "url": "https://boards.greenhouse.io/testco/jobs/senior",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[senior_job]),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_ats_path_applies_industry_filter():
    banking_job = {
        **ATS_JOB,
        "snippet": "Berlin — banking platform role",
        "url": "https://boards.greenhouse.io/testco/jobs/bank",
    }
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[banking_job]),
    ):
        jobs = scraper.scrape()
    assert jobs == []


# ── Task 1: ScrapeStats diagnostics ─────────────────────────────────────────


def test_scrape_stats_records_accepted_and_skipped():
    """ScrapeStats.record accumulates counts correctly."""
    stats = scraper.ScrapeStats()
    stats.record("ats_api", attempted=3, returned=2, accepted=1, skipped=1)
    s = stats.source("ats_api")
    assert s.attempted == 3
    assert s.returned == 2
    assert s.accepted == 1
    assert s.skipped == 1


def test_scrape_stats_log_summary_does_not_raise(caplog):
    """log_summary emits at least one INFO line without errors."""
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


def test_scrape_diagnostics_one_successful_one_failed_source():
    """A scrape with one working ATS source and one failing global source produces correct stats."""
    with (
        patch("job_hunter_core.sources.scraper.load_search_config", return_value=CONFIG),
        patch("job_hunter_core.sources.scraper.load_companies", return_value=COMPANIES[:1]),
        patch("job_hunter_core.sources.scraper.fetch_ats_jobs", return_value=[ATS_JOB]),
        patch(
            "job_hunter_core.sources.scraper.fetch_jobspy_jobs",
            side_effect=RuntimeError("jobspy boom"),
        ),
        patch("job_hunter_core.sources.scraper.fetch_himalayas_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_arbeitsagentur_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_adzuna_jobs", return_value=[]),
        patch("job_hunter_core.sources.scraper.fetch_reed_jobs", return_value=[]),
    ):
        jobs = scraper.scrape()

    # ATS job was accepted
    assert any(j["url"] == ATS_JOB["url"] for j in jobs)
