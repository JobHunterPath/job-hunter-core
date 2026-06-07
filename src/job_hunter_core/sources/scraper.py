"""Hybrid job scraper.

The fallback order is intentionally conservative:
  1. Direct ATS APIs where available.
  2. Static career-page scraping with requests + BeautifulSoup.
  3. Playwright rendering for JavaScript-heavy career pages.
  4. Search providers: SearXNG, Brave, Tavily, Exa.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import requests  # noqa: F401
import yaml

from job_hunter_core.core.config import (
    ADZUNA_API_KEY,
    ADZUNA_APP_ID,
    JOOBLE_API_KEY,
    RAPIDAPI_KEY,
    REED_API_KEY,
    load_api_config,
)
from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.sources.adzuna_source import fetch_adzuna_jobs
from job_hunter_core.sources.ai_web_search import fetch_ai_web_search_jobs
from job_hunter_core.sources.arbeitsagentur_source import fetch_arbeitsagentur_jobs
from job_hunter_core.sources.ats import fetch_ats_jobs
from job_hunter_core.sources.himalayas_source import fetch_himalayas_jobs
from job_hunter_core.sources.job_boards import fetch_arbeitnow_jobs, fetch_jsearch_jobs
from job_hunter_core.sources.job_policy import JobPolicy, make_job_filter
from job_hunter_core.sources.jobicy_source import fetch_jobicy_jobs
from job_hunter_core.sources.jobspy_source import fetch_jobspy_jobs
from job_hunter_core.sources.jooble_source import fetch_jooble_jobs
from job_hunter_core.sources.reed_source import fetch_reed_jobs
from job_hunter_core.sources.remoteok_source import fetch_remoteok_jobs
from job_hunter_core.sources.remotive_source import fetch_remotive_jobs
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
from job_hunter_core.sources.the_muse_source import fetch_the_muse_jobs
from job_hunter_core.sources.weworkremotely_source import fetch_weworkremotely_jobs
from job_hunter_core.tracking.discovery_cache import (
    load_cached_candidate_urls,
    load_cached_candidate_urls_with_metadata,
    save_cached_candidate_urls,
)

ROOT = str(REPO_ROOT)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-source yield diagnostics
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SourceStats:
    """Counts for a single named source during one scrape run."""

    attempted: int = 0
    returned: int = 0
    accepted: int = 0
    skipped: int = 0
    failed: int = 0
    exhausted: int = 0
    cached: int = 0


class ScrapeStats:
    """Accumulates per-source statistics during a scrape run.

    Thread-safe: individual source stat objects are created before the
    parallel phase and are only written by their owning thread (company
    processing is per-company) or under the main thread for global sources.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: dict[str, SourceStats] = {}

    def source(self, name: str) -> SourceStats:
        with self._lock:
            if name not in self._sources:
                self._sources[name] = SourceStats()
            return self._sources[name]

    def record(
        self,
        name: str,
        *,
        attempted: int = 0,
        returned: int = 0,
        accepted: int = 0,
        skipped: int = 0,
        failed: int = 0,
        exhausted: int = 0,
        cached: int = 0,
    ) -> None:
        s = self.source(name)
        with self._lock:
            s.attempted += attempted
            s.returned += returned
            s.accepted += accepted
            s.skipped += skipped
            s.failed += failed
            s.exhausted += exhausted
            s.cached += cached

    def log_summary(self, *, ats_only: bool = False) -> None:
        """Log a compact per-source summary at INFO level."""
        with self._lock:
            sources = dict(self._sources)
        if not sources:
            logger.info("[scraper][diag] no sources recorded")
            return
        header = "[scraper][diag] source yield summary:"
        if ats_only:
            header += " mode=ats-only"
        lines = [header]
        for name, s in sorted(sources.items()):
            parts = [f"attempted={s.attempted}", f"returned={s.returned}", f"accepted={s.accepted}"]
            if s.skipped:
                parts.append(f"skipped={s.skipped}")
            if s.failed:
                parts.append(f"failed={s.failed}")
            if s.exhausted:
                parts.append(f"exhausted={s.exhausted}")
            if s.cached:
                parts.append(f"cached={s.cached}")
            lines.append(f"  {name}: {', '.join(parts)}")
        logger.info("\n".join(lines))

    def to_dict(self) -> dict[str, dict]:
        with self._lock:
            return {name: dataclasses.asdict(s) for name, s in self._sources.items()}


def load_search_config() -> dict:
    config_file = os.path.join(ROOT, "config", "search_config.yml")
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info("[scraper] Loaded search configuration from %s", config_file)
    return config


def load_companies(region: str | None = None) -> list[dict]:
    """Load enabled companies from search_config.yml, optionally scoped by region."""
    config = load_search_config()
    excluded = {name.lower() for name in config.get("excluded_companies", [])}
    companies = []

    regions_to_load = [region] if region else config.get("regions", {}).keys()

    for reg in regions_to_load:
        if reg not in config.get("regions", {}):
            logger.warning("[scraper] Region %r not found in search_config.yml", reg)
            continue

        region_config = config["regions"][reg]
        if not region_config.get("enabled", True):
            logger.info("[scraper] Region %r is disabled. Skipping.", reg)
            continue

        location = region_config.get("location", "")
        loaded = 0
        for company in region_config.get("companies", []):
            if company["name"].lower() in excluded:
                logger.info("[scraper] Skipping excluded company: %s", company["name"])
                continue
            companies.append(
                {
                    **company,
                    "region": reg,
                    "location": location,
                    "country": region_config.get("country", ""),
                    "search_lang": region_config.get("search_lang", ""),
                    "_region_config": region_config,
                }
            )
            loaded += 1

        logger.info(
            "[scraper] Loaded %s companies from region %r (location=%r)",
            loaded,
            reg,
            location,
        )

    logger.info("[scraper] Total: %s companies", len(companies))
    return companies


def build_queries(companies: list[dict], config: dict) -> list[tuple[str, str, str]]:
    """Build search queries. Returns (query, company_name, location)."""
    queries = []
    job_titles = config.get("global_search", {}).get("job_titles", [])
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", [])
    exclusions = " ".join(f'-"{term}"' for term in excluded_title_terms)

    if not job_titles:
        logger.warning("[scraper] global_search.job_titles is empty; no search queries built")
        return queries

    for company in companies:
        url = company["career_url"]
        name = company["name"]
        location = company.get("location", "")

        for title in job_titles:
            query = f'"{title}" site:{url}'
            if location:
                query += f' "{location}"'
            if exclusions:
                query += f" {exclusions}"
            queries.append((query, name, location or "global"))

    logger.info("[scraper] Built %s search queries for %s companies", len(queries), len(companies))
    return queries


def is_valid_job_url(url: str) -> bool:
    """Return False for root/listing pages that are not individual job postings."""
    return JobPolicy({}).is_valid_job_url(url)


def is_excluded_url(url: str, config: dict) -> bool:
    """Return True when caller-configured URL patterns identify non-posting pages."""
    return JobPolicy(config).is_excluded_url(url)


def is_stale_posting(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_stale_posting(title, snippet)


def is_too_senior(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_too_senior(title, snippet)


def is_excluded(snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_excluded_industry(snippet)


def is_german(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_german(title, snippet)


def is_excluded_language(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_excluded_language(title, snippet)


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
        host = netloc.lower().lstrip("www.")
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
                raw = search_web(query, company_region_config, count=10)
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
        jobspy_jobs = list(fetch_jobspy_jobs(title_filters, enabled_regions, config))
        stats.record("jobspy", returned=len(jobspy_jobs))
        jobspy_accepted = 0
        for job in jobspy_jobs:
            if add_job(job, cache_candidate=True):
                jobspy_accepted += 1
        stats.record("jobspy", accepted=jobspy_accepted, skipped=len(jobspy_jobs) - jobspy_accepted)
    except Exception as e:
        stats.record("jobspy", failed=1)
        logger.warning("[scraper] JobSpy failed: %s", e)

    stats.record("himalayas", attempted=1)
    try:
        him_jobs = list(fetch_himalayas_jobs(title_filters, enabled_regions, config))
        stats.record("himalayas", returned=len(him_jobs))
        him_accepted = 0
        for job in him_jobs:
            if add_job(job, cache_candidate=True):
                him_accepted += 1
        stats.record("himalayas", accepted=him_accepted, skipped=len(him_jobs) - him_accepted)
    except Exception as e:
        stats.record("himalayas", failed=1)
        logger.warning("[scraper] Himalayas failed: %s", e)

    try:
        for job in fetch_remotive_jobs(title_filters, enabled_regions, config):
            add_job(job, cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] Remotive failed: %s", e)

    try:
        for job in fetch_the_muse_jobs(title_filters, enabled_regions, config):
            add_job(job, cache_candidate=True)
    except Exception as e:
        logger.warning("[scraper] The Muse failed: %s", e)

    stats.record("jobicy", attempted=1)
    try:
        jobicy_jobs = list(fetch_jobicy_jobs(title_filters, enabled_regions, config))
        stats.record("jobicy", returned=len(jobicy_jobs))
        jobicy_accepted = 0
        for job in jobicy_jobs:
            if add_job(job, cache_candidate=True):
                jobicy_accepted += 1
        stats.record("jobicy", accepted=jobicy_accepted, skipped=len(jobicy_jobs) - jobicy_accepted)
    except Exception as e:
        stats.record("jobicy", failed=1)
        logger.warning("[scraper] Jobicy failed: %s", e)

    stats.record("remoteok", attempted=1)
    try:
        remoteok_jobs = list(fetch_remoteok_jobs(title_filters, enabled_regions, config))
        stats.record("remoteok", returned=len(remoteok_jobs))
        remoteok_accepted = 0
        for job in remoteok_jobs:
            if add_job(job, cache_candidate=True):
                remoteok_accepted += 1
        stats.record(
            "remoteok", accepted=remoteok_accepted, skipped=len(remoteok_jobs) - remoteok_accepted
        )
    except Exception as e:
        stats.record("remoteok", failed=1)
        logger.warning("[scraper] RemoteOK failed: %s", e)

    stats.record("weworkremotely", attempted=1)
    try:
        wwr_jobs = list(fetch_weworkremotely_jobs(title_filters, enabled_regions, config))
        stats.record("weworkremotely", returned=len(wwr_jobs))
        wwr_accepted = 0
        for job in wwr_jobs:
            if add_job(job, cache_candidate=True):
                wwr_accepted += 1
        stats.record("weworkremotely", accepted=wwr_accepted, skipped=len(wwr_jobs) - wwr_accepted)
    except Exception as e:
        stats.record("weworkremotely", failed=1)
        logger.warning("[scraper] WeWorkRemotely failed: %s", e)

    stats.record("jooble", attempted=1)
    try:
        jooble_jobs = list(
            fetch_jooble_jobs(title_filters, enabled_regions, config, JOOBLE_API_KEY)
        )
        stats.record("jooble", returned=len(jooble_jobs))
        jooble_accepted = 0
        for job in jooble_jobs:
            if add_job(job, cache_candidate=True):
                jooble_accepted += 1
        stats.record("jooble", accepted=jooble_accepted, skipped=len(jooble_jobs) - jooble_accepted)
    except Exception as e:
        stats.record("jooble", failed=1)
        logger.warning("[scraper] Jooble failed: %s", e)

    stats.record("arbeitsagentur", attempted=1)
    try:
        aa_jobs = list(fetch_arbeitsagentur_jobs(title_filters, enabled_regions, config))
        stats.record("arbeitsagentur", returned=len(aa_jobs))
        aa_accepted = 0
        for job in aa_jobs:
            if add_job(job, cache_candidate=True):
                aa_accepted += 1
        stats.record("arbeitsagentur", accepted=aa_accepted, skipped=len(aa_jobs) - aa_accepted)
    except Exception as e:
        stats.record("arbeitsagentur", failed=1)
        logger.warning("[scraper] Arbeitsagentur failed: %s", e)

    boards_cfg = load_api_config().get("http", {}).get("job_boards", {})

    for region_name, region_config in enabled_regions.items():
        board_location = region_config.get("location", "")
        if boards_cfg.get("arbeitnow", {}).get("enabled", False):
            max_pages = boards_cfg["arbeitnow"].get("max_pages", 3)
            logger.info(
                "[scraper] Arbeitnow: region=%r, location=%r, max_pages=%s",
                region_name,
                board_location,
                max_pages,
            )
            stats.record("arbeitnow", attempted=1)
            arbeitnow_jobs = list(
                fetch_arbeitnow_jobs(title_filters, board_location, max_pages, excluded_title_terms)
            )
            stats.record("arbeitnow", returned=len(arbeitnow_jobs))
            an_accepted = 0
            for job in arbeitnow_jobs:
                if add_job(job):
                    an_accepted += 1
            stats.record(
                "arbeitnow", accepted=an_accepted, skipped=len(arbeitnow_jobs) - an_accepted
            )

        if boards_cfg.get("jsearch", {}).get("enabled", False):
            num_pages = boards_cfg["jsearch"].get("num_pages", 1)
            logger.info(
                "[scraper] JSearch: region=%r, location=%r, titles=%s",
                region_name,
                board_location,
                title_filters,
            )
            stats.record("jsearch", attempted=1)
            jsearch_jobs = list(
                fetch_jsearch_jobs(
                    title_filters,
                    board_location,
                    RAPIDAPI_KEY,
                    num_pages,
                    excluded_title_terms,
                    region_config.get("country", ""),
                    region_config.get("search_lang", ""),
                )
            )
            stats.record("jsearch", returned=len(jsearch_jobs))
            js_accepted = 0
            for job in jsearch_jobs:
                if add_job(job):
                    js_accepted += 1
            stats.record("jsearch", accepted=js_accepted, skipped=len(jsearch_jobs) - js_accepted)

    stats.record("adzuna", attempted=1)
    try:
        az_jobs = list(
            fetch_adzuna_jobs(title_filters, enabled_regions, config, ADZUNA_APP_ID, ADZUNA_API_KEY)
        )
        stats.record("adzuna", returned=len(az_jobs))
        az_accepted = 0
        for job in az_jobs:
            if add_job(job):
                az_accepted += 1
        stats.record("adzuna", accepted=az_accepted, skipped=len(az_jobs) - az_accepted)
    except Exception as e:
        stats.record("adzuna", failed=1)
        logger.warning("[scraper] Adzuna failed: %s", e)

    stats.record("reed", attempted=1)
    try:
        reed_jobs = list(fetch_reed_jobs(title_filters, enabled_regions, config, REED_API_KEY))
        stats.record("reed", returned=len(reed_jobs))
        reed_accepted = 0
        for job in reed_jobs:
            if add_job(job):
                reed_accepted += 1
        stats.record("reed", accepted=reed_accepted, skipped=len(reed_jobs) - reed_accepted)
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

    # --- revalidation fallback (Task 5) ---
    _maybe_revalidate_cache(config, api_cfg_loaded, results, cached_candidate_urls, add_job, stats)

    stats.log_summary(ats_only=all_providers_exhausted())
    logger.info("[scraper] Complete: %s jobs found", len(results))
    if candidate_cache_updates:
        save_cached_candidate_urls(cached_candidate_urls | candidate_cache_updates)
        logger.info(
            "[scraper] Cached %s new discovery candidate URL(s)", len(candidate_cache_updates)
        )
    return results


# ---------------------------------------------------------------------------
# Task 5: Cache revalidation as a bounded fallback
# ---------------------------------------------------------------------------


def _maybe_revalidate_cache(
    config: dict,
    _api_cfg: dict,
    results: list[dict],
    cached_candidate_urls: set[str],
    add_job: Any,
    stats: ScrapeStats,
) -> None:
    """Re-check cached broad-discovery URLs when live yield is below a threshold.

    Controlled by ``scraping.cache_revalidation`` in search_config.yml:
      enabled: false          # disabled by default
      threshold: 5            # only run when fewer than this many live results
      max_urls: 20            # upper bound on how many cached URLs to check
    """
    rev_cfg = config.get("scraping", {}).get("cache_revalidation", {}) or {}
    if not rev_cfg.get("enabled", False):
        return

    threshold = int(rev_cfg.get("threshold", 5))
    max_urls = int(rev_cfg.get("max_urls", 20))

    if len(results) >= threshold:
        logger.debug(
            "[scraper][revalidation] skipped: %d live results >= threshold %d",
            len(results),
            threshold,
        )
        return

    if not cached_candidate_urls:
        logger.debug("[scraper][revalidation] no cached URLs to revalidate")
        return

    # Load with metadata so we can pick the most-recently-seen URLs first.
    try:
        all_cached = load_cached_candidate_urls_with_metadata()
    except Exception:
        # Fallback: use the flat set already loaded
        all_cached = {url: {} for url in cached_candidate_urls}

    # Skip URLs already found in this run.
    result_urls = {canonicalize_url(j.get("url", "")) for j in results}
    candidates = [url for url in all_cached if url not in result_urls]
    candidates = candidates[:max_urls]

    if not candidates:
        logger.debug("[scraper][revalidation] all cached URLs already in results")
        return

    logger.info(
        "[scraper][revalidation] live yield %d < threshold %d; revalidating up to %d cached URL(s)",
        len(results),
        threshold,
        len(candidates),
    )
    stats.record("cache_revalidation", attempted=len(candidates))

    accepted = 0
    for url in candidates:
        meta = all_cached.get(url) or {}
        job = {
            "title": meta.get("title", ""),
            "company": meta.get("company", ""),
            "url": url,
            "posted": meta.get("posted", ""),
            "snippet": meta.get("snippet", ""),
            "source": "cache_revalidation",
        }
        if add_job(job, cache_candidate=False):
            accepted += 1

    stats.record("cache_revalidation", accepted=accepted, skipped=len(candidates) - accepted)
    logger.info(
        "[scraper][revalidation] accepted %d / %d revalidated URL(s)", accepted, len(candidates)
    )


if __name__ == "__main__":
    jobs = scrape()
    print(json.dumps(jobs, indent=2))
