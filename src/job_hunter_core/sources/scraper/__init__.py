"""Hybrid job scraper.

The scraper is source-first: every configured title is searched across every
enabled source for every enabled region, then normalized through one policy gate.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any
from urllib.parse import urlparse

import requests  # noqa: F401

from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.sources.adzuna_source import AdzunaSource
from job_hunter_core.sources.ai_web_search import fetch_ai_web_search_jobs
from job_hunter_core.sources.arbeitsagentur_source import ArbeitsagenturSource
from job_hunter_core.sources.careerjet_source import CareerjetSource
from job_hunter_core.sources.glints_source import GlintsSource
from job_hunter_core.sources.gulftalent_source import GulfTalentSource
from job_hunter_core.sources.himalayas_source import HimalayasSource
from job_hunter_core.sources.job_boards import ArbeitnowSource, JSearchSource
from job_hunter_core.sources.job_policy import make_job_filter
from job_hunter_core.sources.jobbank_source import JobBankSource
from job_hunter_core.sources.jobicy_source import JobicySource
from job_hunter_core.sources.jobspy_source import JobSpySource
from job_hunter_core.sources.jobstreet_source import JobStreetSource
from job_hunter_core.sources.jooble_source import JoobleSource
from job_hunter_core.sources.mycareersfuture_source import MyCareersFutureSource
from job_hunter_core.sources.reed_source import ReedSource
from job_hunter_core.sources.remoteok_source import RemoteOKSource
from job_hunter_core.sources.remotive_source import RemotiveSource
from job_hunter_core.sources.scraper._config import (
    enabled_regions as resolve_enabled_regions,
)
from job_hunter_core.sources.scraper._config import (
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
)
from job_hunter_core.sources.search_providers.preflight import (
    probe_job_sources,
    probe_search_providers,
)
from job_hunter_core.sources.search_providers.router import set_run_disabled
from job_hunter_core.sources.the_muse_source import TheMuseSource
from job_hunter_core.sources.usajobs_source import USAJobsSource
from job_hunter_core.sources.weworkremotely_source import WeWorkRemotelySource
from job_hunter_core.sources.workingnomads_source import WorkingNomadsSource
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
    """Scrape jobs from all enabled sources for configured titles and regions."""
    config = load_search_config()
    stats = ScrapeStats()

    # Probe all search providers once at run start. Dead or quota-exhausted providers
    # are disabled for the entire run.
    _run_disabled = probe_search_providers()
    set_run_disabled(_run_disabled)

    global_cfg = config.get("global_search", {})
    title_filters = global_cfg.get("job_titles", [])
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", [])
    enabled_regions = resolve_enabled_regions(config, region)
    source_preflight = probe_job_sources(title_filters, enabled_regions, config)
    source_skip_logged: set[str] = set()

    def _source_available(name: str) -> bool:
        result = source_preflight.get(name)
        if result is None or result.status == "ok":
            return True
        if name not in source_skip_logged:
            source_skip_logged.add(name)
            logger.info(
                "[preflight] %s: disabled for this run (%s%s)",
                name,
                result.status,
                f": {result.reason}" if result.reason else "",
            )
        return False

    results: list[dict] = []
    seen_urls: set[str] = set()
    cached_candidate_urls = load_cached_candidate_urls()
    candidate_cache_updates: set[str] = set()
    lock = threading.Lock()
    add_job = _make_filter(
        config,
        seen_urls,
        results,
        title_filters,
        lock,
        cached_candidate_urls,
        candidate_cache_updates,
    )

    if not title_filters:
        logger.warning("[scraper] global_search.job_titles is empty; no source searches run")
        return []
    if not enabled_regions:
        logger.warning("[scraper] No enabled regions found in search_config.yml")
        return []

    stats.record("ats_search_discovery", attempted=1)
    try:
        discovery_jobs = list(
            discover_ats_jobs_by_search(
                title_filters,
                enabled_regions,
                excluded_title_terms,
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

    def _collect_source(name: str, fetcher, *, cache_candidate: bool = True) -> None:
        stats.record(name, attempted=1)
        if not _source_available(name):
            return
        try:
            postings = fetcher()
            stats.record(name, returned=len(postings))
            accepted = 0
            for jp in postings:
                if add_job(jp.to_dict(), cache_candidate=cache_candidate):
                    accepted += 1
            stats.record(name, accepted=accepted, skipped=len(postings) - accepted)
        except Exception as e:
            stats.record(name, failed=1)
            logger.warning("[scraper] %s failed: %s", name, e)

    _collect_source(
        "jobspy",
        lambda: JobSpySource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "himalayas",
        lambda: HimalayasSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "remotive",
        lambda: RemotiveSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "the_muse",
        lambda: TheMuseSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "jobicy",
        lambda: JobicySource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "remoteok",
        lambda: RemoteOKSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "weworkremotely",
        lambda: WeWorkRemotelySource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "mycareersfuture",
        lambda: MyCareersFutureSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "jobbank",
        lambda: JobBankSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "glints",
        lambda: GlintsSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "gulftalent",
        lambda: GulfTalentSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "jobstreet",
        lambda: JobStreetSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "jooble",
        lambda: JoobleSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "arbeitsagentur",
        lambda: ArbeitsagenturSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "arbeitnow",
        lambda: ArbeitnowSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "jsearch",
        lambda: JSearchSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "adzuna",
        lambda: AdzunaSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "reed",
        lambda: ReedSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "careerjet",
        lambda: CareerjetSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "workingnomads",
        lambda: WorkingNomadsSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )
    _collect_source(
        "usajobs",
        lambda: USAJobsSource().fetch(title_filters, enabled_regions, config),
        cache_candidate=False,
    )

    llm_search_cfg = config.get("llm_job_search", {}) or {}
    if llm_search_cfg.get("enabled", False):
        ai_min_jobs = int(llm_search_cfg.get("trigger_threshold", 0) or 0)
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
                    if add_job(job, cache_candidate=True):
                        ai_accepted += 1
                stats.record(
                    "ai_web_search",
                    accepted=ai_accepted,
                    skipped=len(ai_jobs) - ai_accepted,
                )
            except Exception as e:
                stats.record("ai_web_search", failed=1)
                logger.warning("[scraper] AI web search failed: %s", e)
    else:
        stats.record("ai_web_search", attempted=1)
        stats.record("ai_web_search", skipped=1)

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
