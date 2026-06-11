"""Hybrid job scraper.

The fallback order is intentionally conservative:
  1. Direct ATS APIs where available.
  2. Static career-page scraping with requests + BeautifulSoup.
  3. Playwright rendering for JavaScript-heavy career pages.
  4. Search providers: SearXNG, Brave, Tavily, Exa.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import requests  # noqa: F401

from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.core.config import (
    load_api_config,
)
from job_hunter_core.sources.adzuna_source import AdzunaSource
from job_hunter_core.sources.ai_web_search import fetch_ai_web_search_jobs
from job_hunter_core.sources.arbeitsagentur_source import ArbeitsagenturSource
from job_hunter_core.sources.ats import fetch_ats_jobs
from job_hunter_core.sources.eures_source import EURESSource
from job_hunter_core.sources.glints_source import GlintsSource
from job_hunter_core.sources.gulftalent_source import GulfTalentSource
from job_hunter_core.sources.himalayas_source import HimalayasSource
from job_hunter_core.sources.irishjobs_source import IrishJobsSource
from job_hunter_core.sources.job_boards import ArbeitnowSource, JSearchSource
from job_hunter_core.sources.job_policy import JobPolicy, make_job_filter
from job_hunter_core.sources.jobbank_source import JobBankSource
from job_hunter_core.sources.jobicy_source import JobicySource
from job_hunter_core.sources.jobspy_source import JobSpySource
from job_hunter_core.sources.jobstreet_source import JobStreetSource
from job_hunter_core.sources.jooble_source import JoobleSource
from job_hunter_core.sources.mycareersfuture_source import MyCareersFutureSource
from job_hunter_core.sources.naukrigulf_source import NaukriGulfSource
from job_hunter_core.sources.reed_source import ReedSource
from job_hunter_core.sources.remoteok_source import RemoteOKSource
from job_hunter_core.sources.remotive_source import RemotiveSource
from job_hunter_core.sources.scraper._config import (
    build_queries,
    load_companies,
    load_search_config,
)
from job_hunter_core.sources.scraper._policy import (
    is_excluded as is_excluded,
)
from job_hunter_core.sources.scraper._policy import (
    is_excluded_language as is_excluded_language,
)
from job_hunter_core.sources.scraper._policy import (
    is_excluded_url as is_excluded_url,
)
from job_hunter_core.sources.scraper._policy import (
    is_german as is_german,
)
from job_hunter_core.sources.scraper._policy import (
    is_stale_posting as is_stale_posting,
)
from job_hunter_core.sources.scraper._policy import (
    is_too_senior as is_too_senior,
)
from job_hunter_core.sources.scraper._policy import (
    is_valid_job_url as is_valid_job_url,
)
from job_hunter_core.sources.scraper._stats import ScrapeStats
from job_hunter_core.sources.scraper._stats import SourceStats as SourceStats
from job_hunter_core.sources.search_providers import (
    BraveProvider,
    all_providers_exhausted,
    canonicalize_url,  # noqa: F401
    discover_ats_jobs_by_search,
    fetch_firecrawl_career_jobs,
    fetch_lightpanda_career_jobs,
    fetch_playwright_career_jobs,
    fetch_static_career_jobs,
    search_web,
)
from job_hunter_core.sources.search_providers.preflight import probe_search_providers
from job_hunter_core.sources.search_providers.router import set_run_disabled
from job_hunter_core.sources.the_muse_source import TheMuseSource
from job_hunter_core.sources.weworkremotely_source import WeWorkRemotelySource
from job_hunter_core.sources.wttj_source import WTTJSource
from job_hunter_core.tracking.discovery_cache import (
    load_cached_candidate_urls,
    save_cached_candidate_urls,
)

ROOT = str(REPO_ROOT)
logger = logging.getLogger(__name__)


def _url_matches_career_site(career_url: str, result_url: str) -> bool:
    """Return True if result_url plausibly came from career_url's site.

    Guards against search providers ignoring the site: operator and returning
    results from unrelated domains (e.g. querying site:gf.com/careers but
    getting back job-boards.greenhouse.io/anthropic).
    """

    def _parsed(url: str):
        if "://" not in url:
            url = "https://" + url
        return urlparse(url)

    def _etld1(netloc: str) -> str:
        host = netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    career = _parsed(career_url)
    result = _parsed(result_url)

    if _etld1(career.netloc) != _etld1(result.netloc):
        return False

    career_path = career.path.rstrip("/")
    if career_path and career_path != "/":
        if not result.path.startswith(career_path):
            return False

    return True


def brave_search(query: str, region_config: dict, count: int | None = None) -> list[dict]:
    """Compatibility wrapper for tests/tools that call Brave directly."""
    count = count or 10
    try:
        results = BraveProvider().search(query, region_config, count=count)
    except Exception as e:
        logger.error("[scraper] Error during Brave Search: %s", e)
        raise
    return [
        {
            "url": result.url,
            "title": result.title,
            "description": result.description,
            "source": result.source,
        }
        for result in results
    ]


def _make_filter(
    config: dict,
    seen_urls: set[str],
    results: list[dict],
    title_filters: list[str],
    lock: threading.Lock | None = None,
    cached_candidate_urls: set[str] | None = None,
    candidate_cache_updates: set[str] | None = None,
) -> Any:
    return make_job_filter(
        config,
        seen_urls,
        results,
        title_filters,
        lock,
        cached_candidate_urls,
        candidate_cache_updates,
    )


def scrape(region: str | None = None) -> list[dict]:
    """Scrape jobs for configured companies and global boards."""
    config = load_search_config()
    companies = load_companies(region)
    stats = ScrapeStats()

    # Probe all search providers once at run start. Dead or quota-exhausted providers
    # are disabled for the entire run without repeated file reads per company.
    _run_disabled = probe_search_providers()
    set_run_disabled(_run_disabled)

    global_cfg = config.get("global_search", {})
    title_filters = global_cfg.get("job_titles", [])
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", [])
    if region:
        region_cfg = config.get("regions", {}).get(region)
        enabled_regions = (
            {region: region_cfg} if region_cfg and region_cfg.get("enabled", True) else {}
        )
    else:
        enabled_regions = {
            name: rc for name, rc in config.get("regions", {}).items() if rc.get("enabled", True)
        }

    results: list[dict] = []
    seen_urls: set[str] = set()
    cached_candidate_urls = load_cached_candidate_urls()
    candidate_cache_updates: set[str] = set()
    lock = threading.Lock()
    policy = JobPolicy(config)
    add_job = _make_filter(
        config,
        seen_urls,
        results,
        title_filters,
        lock,
        cached_candidate_urls,
        candidate_cache_updates,
    )

    if not companies:
        logger.warning("[scraper] No companies to scrape. Check search_config.yml")

    scraping_cfg = config.get("scraping", {})
    max_workers = int(scraping_cfg.get("max_workers", 10))

    def _process_company(company: dict) -> None:
        company_region = company.get("region", "")
        company_region_config = company.get("_region_config") or {
            "location": company.get("location", ""),
            "country": company.get("country", ""),
            "search_lang": company.get("search_lang", ""),
        }
        stats.record("ats_api", attempted=1)
        ats_jobs = fetch_ats_jobs(
            company, company.get("location", ""), title_filters, excluded_title_terms
        )
        if ats_jobs is not None:
            stats.record("ats_api", returned=len(ats_jobs))
            accepted = 0
            for job in ats_jobs:
                if add_job({**job, "region": company_region}):
                    accepted += 1
            stats.record("ats_api", accepted=accepted, skipped=len(ats_jobs) - accepted)
            return

        direct_found = 0
        stats.record("static_career_page", attempted=1)
        try:
            static_jobs = list(
                fetch_static_career_jobs(company, title_filters, excluded_title_terms)
            )
            stats.record("static_career_page", returned=len(static_jobs))
            for job in static_jobs:
                if add_job({**job, "region": company_region}):
                    direct_found += 1
            stats.record(
                "static_career_page",
                accepted=direct_found,
                skipped=len(static_jobs) - direct_found,
            )
        except Exception as e:
            stats.record("static_career_page", failed=1)
            logger.debug("[scraper] HTTP career scrape failed for %s: %s", company["name"], e)

        if direct_found == 0:
            stats.record("lightpanda_career_page", attempted=1)
            try:
                lp_jobs = list(
                    fetch_lightpanda_career_jobs(company, title_filters, excluded_title_terms)
                )
                stats.record("lightpanda_career_page", returned=len(lp_jobs))
                lp_accepted = 0
                for job in lp_jobs:
                    if add_job({**job, "region": company_region}):
                        direct_found += 1
                        lp_accepted += 1
                stats.record(
                    "lightpanda_career_page",
                    accepted=lp_accepted,
                    skipped=len(lp_jobs) - lp_accepted,
                )
            except Exception as e:
                stats.record("lightpanda_career_page", failed=1)
                logger.debug(
                    "[scraper] Lightpanda career scrape failed for %s: %s", company["name"], e
                )

        if direct_found == 0:
            stats.record("playwright_career_page", attempted=1)
            try:
                pw_jobs = list(
                    fetch_playwright_career_jobs(company, title_filters, excluded_title_terms)
                )
                stats.record("playwright_career_page", returned=len(pw_jobs))
                pw_accepted = 0
                for job in pw_jobs:
                    if add_job({**job, "region": company_region}):
                        direct_found += 1
                        pw_accepted += 1
                stats.record(
                    "playwright_career_page",
                    accepted=pw_accepted,
                    skipped=len(pw_jobs) - pw_accepted,
                )
            except Exception as e:
                stats.record("playwright_career_page", failed=1)
                logger.debug(
                    "[scraper] Playwright career scrape failed for %s: %s", company["name"], e
                )

        if direct_found == 0:
            stats.record("firecrawl_career_page", attempted=1)
            try:
                fc_jobs = list(
                    fetch_firecrawl_career_jobs(company, title_filters, excluded_title_terms)
                )
                stats.record("firecrawl_career_page", returned=len(fc_jobs))
                fc_accepted = 0
                for job in fc_jobs:
                    if add_job({**job, "region": company_region}):
                        direct_found += 1
                        fc_accepted += 1
                stats.record(
                    "firecrawl_career_page",
                    accepted=fc_accepted,
                    skipped=len(fc_jobs) - fc_accepted,
                )
            except Exception as e:
                stats.record("firecrawl_career_page", failed=1)
                logger.debug(
                    "[scraper] Firecrawl career scrape failed for %s: %s", company["name"], e
                )

        if direct_found:
            return

        if all_providers_exhausted():
            logger.debug("[scraper] %s: search skipped (ATS-only mode)", company["name"])
            return

        for query, company_name, _ in build_queries([company], config):
            stats.record("search_fallback", attempted=1)
            try:
                # Restrict per-company fallback to SearXNG only — paid API keys
                # (Brave/Tavily/Exa) are reserved for the global ATS discovery phase.
                raw = search_web(
                    query,
                    company_region_config,
                    count=10,
                    allowed={"searxng"},
                    disabled=_run_disabled,
                )
                stats.record("search_fallback", returned=len(raw))
            except Exception as e:
                stats.record("search_fallback", failed=1)
                logger.warning("[scraper] Search error for %s: %s", company_name, e)
                continue

            filtered_count = 0
            accepted_count = 0
            for item in raw:
                url = item.get("url", "")
                title = item.get("title", "")
                snippet = item.get("description", "")

                if not url:
                    continue
                if not _url_matches_career_site(company["career_url"], url):
                    logger.debug(
                        "[scraper] Off-target result skipped (career=%s, got %s)",
                        company["career_url"],
                        url,
                    )
                    filtered_count += 1
                    continue
                if not policy.accepts_search_result_url(url, title, snippet):
                    filtered_count += 1
                    continue

                if add_job(
                    {
                        "title": title,
                        "company": company_name,
                        "url": url,
                        "posted": "",
                        "snippet": snippet,
                        "source": item.get("source", "Search fallback"),
                        "query": query,
                        "region": company_region,
                    }
                ):
                    accepted_count += 1

            stats.record(
                "search_fallback",
                accepted=accepted_count,
                skipped=filtered_count,
            )
            if filtered_count > 0:
                logger.debug(
                    "[scraper] Filtered %s ineligible results from %s", filtered_count, company_name
                )

    total_scrape_timeout = int(scraping_cfg.get("total_timeout_seconds", 1800))
    total_companies = len(companies)
    company_counter = 0
    company_counter_lock = threading.Lock()

    def _process_company_tracked(company: dict) -> None:
        nonlocal company_counter
        with company_counter_lock:
            company_counter += 1
            idx = company_counter
        logger.info("[scraper] [%d/%d] %s", idx, total_companies, company["name"])
        _process_company(company)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_company_tracked, company): company for company in companies
        }
        try:
            for future in as_completed(futures, timeout=total_scrape_timeout):
                company = futures[future]
                try:
                    future.result()
                except Exception as e:
                    stats.record("ats_api", failed=1)
                    logger.warning("[scraper] Error processing %s: %s", company.get("name", "?"), e)
        except TimeoutError:
            logger.warning(
                "[scraper] Company scraping hit %ss total timeout, proceeding with partial results",
                total_scrape_timeout,
            )

    stats.record("ats_search_discovery", attempted=1)
    try:
        discovery_jobs = list(
            discover_ats_jobs_by_search(
                title_filters,
                enabled_regions,
                excluded_title_terms,
                ats_discovery_cfg=config.get("ats_discovery", {}),
                disabled=_run_disabled,
            )
        )
        stats.record("ats_search_discovery", returned=len(discovery_jobs))
        disc_accepted = 0
        for job in discovery_jobs:
            if add_job(job, cache_candidate=True):
                disc_accepted += 1
        stats.record(
            "ats_search_discovery",
            accepted=disc_accepted,
            skipped=len(discovery_jobs) - disc_accepted,
        )
    except Exception as e:
        stats.record("ats_search_discovery", failed=1)
        logger.warning("[scraper] ATS search discovery failed: %s", e)

    stats.record("jobspy", attempted=1)
    try:
        jobspy_postings = JobSpySource().fetch(title_filters, enabled_regions, config)
        stats.record("jobspy", returned=len(jobspy_postings))
        jobspy_accepted = 0
        for jp in jobspy_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                jobspy_accepted += 1
        stats.record(
            "jobspy", accepted=jobspy_accepted, skipped=len(jobspy_postings) - jobspy_accepted
        )
    except Exception as e:
        stats.record("jobspy", failed=1)
        logger.warning("[scraper] JobSpy failed: %s", e)

    stats.record("himalayas", attempted=1)
    try:
        him_postings = HimalayasSource().fetch(title_filters, enabled_regions, config)
        stats.record("himalayas", returned=len(him_postings))
        him_accepted = 0
        for jp in him_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                him_accepted += 1
        stats.record("himalayas", accepted=him_accepted, skipped=len(him_postings) - him_accepted)
    except Exception as e:
        stats.record("himalayas", failed=1)
        logger.warning("[scraper] Himalayas failed: %s", e)

    try:
        for jp in RemotiveSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] Remotive failed: %s", e)

    try:
        for jp in TheMuseSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] The Muse failed: %s", e)

    stats.record("jobicy", attempted=1)
    try:
        jobicy_postings = JobicySource().fetch(title_filters, enabled_regions, config)
        stats.record("jobicy", returned=len(jobicy_postings))
        jobicy_accepted = 0
        for jp in jobicy_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                jobicy_accepted += 1
        stats.record(
            "jobicy", accepted=jobicy_accepted, skipped=len(jobicy_postings) - jobicy_accepted
        )
    except Exception as e:
        stats.record("jobicy", failed=1)
        logger.warning("[scraper] Jobicy failed: %s", e)

    stats.record("remoteok", attempted=1)
    try:
        remoteok_postings = RemoteOKSource().fetch(title_filters, enabled_regions, config)
        stats.record("remoteok", returned=len(remoteok_postings))
        remoteok_accepted = 0
        for jp in remoteok_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                remoteok_accepted += 1
        stats.record(
            "remoteok",
            accepted=remoteok_accepted,
            skipped=len(remoteok_postings) - remoteok_accepted,
        )
    except Exception as e:
        stats.record("remoteok", failed=1)
        logger.warning("[scraper] RemoteOK failed: %s", e)

    stats.record("weworkremotely", attempted=1)
    try:
        wwr_postings = WeWorkRemotelySource().fetch(title_filters, enabled_regions, config)
        stats.record("weworkremotely", returned=len(wwr_postings))
        wwr_accepted = 0
        for jp in wwr_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                wwr_accepted += 1
        stats.record(
            "weworkremotely", accepted=wwr_accepted, skipped=len(wwr_postings) - wwr_accepted
        )
    except Exception as e:
        stats.record("weworkremotely", failed=1)
        logger.warning("[scraper] WeWorkRemotely failed: %s", e)

    try:
        for jp in MyCareersFutureSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] MyCareersFuture failed: %s", e)

    try:
        for jp in EURESSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] EURES failed: %s", e)

    try:
        for jp in JobBankSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] JobBank Canada failed: %s", e)

    try:
        for jp in WTTJSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] Welcome to the Jungle failed: %s", e)

    try:
        for jp in GlintsSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] Glints failed: %s", e)

    try:
        for jp in IrishJobsSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] IrishJobs failed: %s", e)

    try:
        for jp in GulfTalentSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] GulfTalent failed: %s", e)

    try:
        for jp in NaukriGulfSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] Naukrigulf failed: %s", e)

    try:
        for jp in JobStreetSource().fetch(title_filters, enabled_regions, config):
            add_job(jp.to_dict(), cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] JobStreet failed: %s", e)

    stats.record("jooble", attempted=1)
    try:
        jooble_postings = JoobleSource().fetch(title_filters, enabled_regions, config)
        stats.record("jooble", returned=len(jooble_postings))
        jooble_accepted = 0
        for jp in jooble_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                jooble_accepted += 1
        stats.record(
            "jooble", accepted=jooble_accepted, skipped=len(jooble_postings) - jooble_accepted
        )
    except Exception as e:
        stats.record("jooble", failed=1)
        logger.warning("[scraper] Jooble failed: %s", e)

    stats.record("arbeitsagentur", attempted=1)
    try:
        aa_postings = ArbeitsagenturSource().fetch(title_filters, enabled_regions, config)
        stats.record("arbeitsagentur", returned=len(aa_postings))
        aa_accepted = 0
        for jp in aa_postings:
            if add_job(jp.to_dict(), cache_candidate=True):
                aa_accepted += 1
        stats.record("arbeitsagentur", accepted=aa_accepted, skipped=len(aa_postings) - aa_accepted)
    except Exception as e:
        stats.record("arbeitsagentur", failed=1)
        logger.warning("[scraper] Arbeitsagentur failed: %s", e)

    stats.record("arbeitnow", attempted=1)
    try:
        arbeitnow_postings = ArbeitnowSource().fetch(title_filters, enabled_regions, config)
        stats.record("arbeitnow", returned=len(arbeitnow_postings))
        an_accepted = 0
        for jp in arbeitnow_postings:
            if add_job(jp.to_dict()):
                an_accepted += 1
        stats.record(
            "arbeitnow", accepted=an_accepted, skipped=len(arbeitnow_postings) - an_accepted
        )
    except Exception as e:
        stats.record("arbeitnow", failed=1)
        logger.warning("[scraper] Arbeitnow failed: %s", e)

    stats.record("jsearch", attempted=1)
    try:
        jsearch_postings = JSearchSource().fetch(title_filters, enabled_regions, config)
        stats.record("jsearch", returned=len(jsearch_postings))
        js_accepted = 0
        for jp in jsearch_postings:
            if add_job(jp.to_dict()):
                js_accepted += 1
        stats.record("jsearch", accepted=js_accepted, skipped=len(jsearch_postings) - js_accepted)
    except Exception as e:
        stats.record("jsearch", failed=1)
        logger.warning("[scraper] JSearch failed: %s", e)

    stats.record("adzuna", attempted=1)
    try:
        az_postings = AdzunaSource().fetch(title_filters, enabled_regions, config)
        stats.record("adzuna", returned=len(az_postings))
        az_accepted = 0
        for jp in az_postings:
            if add_job(jp.to_dict()):
                az_accepted += 1
        stats.record("adzuna", accepted=az_accepted, skipped=len(az_postings) - az_accepted)
    except Exception as e:
        stats.record("adzuna", failed=1)
        logger.warning("[scraper] Adzuna failed: %s", e)

    stats.record("reed", attempted=1)
    try:
        reed_postings = ReedSource().fetch(title_filters, enabled_regions, config)
        stats.record("reed", returned=len(reed_postings))
        reed_accepted = 0
        for jp in reed_postings:
            if add_job(jp.to_dict()):
                reed_accepted += 1
        stats.record("reed", accepted=reed_accepted, skipped=len(reed_postings) - reed_accepted)
    except Exception as e:
        stats.record("reed", failed=1)
        logger.warning("[scraper] Reed failed: %s", e)

    api_cfg_loaded = load_api_config()
    ai_web_cfg = (
        api_cfg_loaded.get("http", {}).get("search_providers", {}).get("ai_web_search", {}) or {}
    )
    ai_min_jobs = int(ai_web_cfg.get("run_if_fewer_than_jobs", 0) or 0)
    if ai_min_jobs > 0 and len(results) >= ai_min_jobs:
        logger.info(
            "[scraper] Skipping AI web search: %s result(s) already meet threshold %s",
            len(results),
            ai_min_jobs,
        )
        stats.record("ai_web_search", skipped=1)
    else:
        stats.record("ai_web_search", attempted=1)
        try:
            ai_jobs = list(fetch_ai_web_search_jobs(title_filters, enabled_regions))
            stats.record("ai_web_search", returned=len(ai_jobs))
            ai_accepted = 0
            for job in ai_jobs:
                if add_job(job, allow_excluded_urls=True, cache_candidate=True):
                    ai_accepted += 1
            stats.record("ai_web_search", accepted=ai_accepted, skipped=len(ai_jobs) - ai_accepted)
        except Exception as e:
            stats.record("ai_web_search", failed=1)
            logger.warning("[scraper] AI web search failed: %s", e)

    stats.log_summary(ats_only=all_providers_exhausted())
    logger.info("[scraper] Complete: %s jobs found", len(results))
    if candidate_cache_updates:
        save_cached_candidate_urls(cached_candidate_urls | candidate_cache_updates)
        logger.info(
            "[scraper] Cached %s new discovery candidate URL(s)", len(candidate_cache_updates)
        )
    return results


if __name__ == "__main__":
    jobs = scrape()
    print(json.dumps(jobs, indent=2))
