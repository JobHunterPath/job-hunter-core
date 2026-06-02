"""Hunt-mode pipeline: scrape, deduplicate, enrich, and dispatch jobs."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from job_hunter_core.core.url_liveness import UrlLivenessCache
from job_hunter_core.pipeline.enrichment import drop_dead_urls_before_enrichment, enrich_snippets
from job_hunter_core.sources.jd_fetcher import fetch_jd
from job_hunter_core.sources.scraper import scrape
from job_hunter_core.sources.search_providers import canonicalize_url
from job_hunter_core.tracking.tracker import filter_new_jobs

logger = logging.getLogger(__name__)


def _jobs_from_hunt(region: str | None = None) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Scrape configured companies/boards, then deduplicate against processed jobs."""
    jobs = scrape(region=region)
    if not jobs:
        return [], set(), set()
    new_jobs, existing_urls, existing_titles = filter_new_jobs(jobs)
    seen_canonical: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for job in new_jobs:
        c = canonicalize_url(job.get("url", ""))
        if not c or c not in seen_canonical:
            if c:
                seen_canonical.add(c)
            deduped.append(job)
    dropped = len(new_jobs) - len(deduped)
    if dropped:
        logger.info("[pipeline] Dropped %s canonical-URL duplicate(s) before enrichment", dropped)
    return deduped, existing_urls, existing_titles


def _drop_dead_urls(
    jobs: list[dict[str, Any]],
    api_cfg: dict[str, Any],
    url_checker: Any = None,
) -> list[dict[str, Any]]:
    return drop_dead_urls_before_enrichment(
        jobs,
        api_cfg,
        url_checker=url_checker or UrlLivenessCache().is_alive,
    )


def _enrich(
    jobs: list[dict[str, Any]], api_cfg: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    return enrich_snippets(jobs, api_cfg, fetcher=fetch_jd)


def run_hunt(
    args: argparse.Namespace,
    api_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    url_liveness: UrlLivenessCache,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """
    Execute the hunt mode: scrape, URL-check, enrich.

    Returns (jobs, existing_urls, existing_titles) ready for downstream processing,
    or ([], set(), set()) when there is nothing to process.
    """
    logger.info("[pipeline] Step 1: Scraping and deduplicating jobs...")
    jobs, existing_urls, existing_titles = _jobs_from_hunt(args.region)
    if not jobs:
        logger.warning("[pipeline] No new jobs found. Exiting.")
        return [], set(), set()

    jobs = _drop_dead_urls(jobs, api_cfg, url_liveness.is_alive)
    if not jobs:
        logger.warning("[pipeline] All scraped jobs failed URL verification before enrichment.")
        return [], set(), set()

    logger.info("[pipeline] Step 1b: Enriching sparse job descriptions...")
    jobs = _enrich(jobs, api_cfg)
    return jobs, existing_urls, existing_titles
