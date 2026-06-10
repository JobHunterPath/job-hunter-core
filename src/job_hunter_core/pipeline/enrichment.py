"""Pre-validation URL and snippet enrichment helpers."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from job_hunter_core.core.config import load_api_config
from job_hunter_core.core.metrics import timed_stage
from job_hunter_core.core.utils import url_is_alive
from job_hunter_core.sources.jd_fetcher import fetch_jd

logger = logging.getLogger(__name__)

_MIN_SNIPPET_CHARS = 300  # snippets shorter than this are considered sparse and trigger enrichment

JDFetcher = Callable[..., dict | None]


def enrich_snippets(
    jobs: list[dict],
    api_cfg: dict | None = None,
    *,
    fetcher: JDFetcher = fetch_jd,
) -> list[dict]:
    """
    Fetch full JD content for jobs with sparse or missing snippets.

    Full JD enrichment is best-effort and preserves input order. Failed fetches
    keep the original job unchanged.
    """
    if api_cfg is None:
        api_cfg = load_api_config()

    enrich_cfg = api_cfg.get("http", {}).get("jd_enrichment", {}) or {}
    max_workers = int(enrich_cfg.get("max_workers", 5))
    skip_patterns = enrich_cfg.get("skip_url_patterns") or [r"linkedin\.com/jobs/"]

    def _should_skip_enrichment(url: str) -> bool:
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in skip_patterns)

    sparse = []
    skipped = 0
    for job in jobs:
        needs_enrichment = (
            not job.get("snippet")
            or len(job.get("snippet", "")) < _MIN_SNIPPET_CHARS
            or job.get("source", "").startswith("Brave")
        )
        if not needs_enrichment:
            continue
        if _should_skip_enrichment(job.get("url", "")):
            skipped += 1
            continue
        sparse.append(job)
    if not sparse:
        if skipped:
            logger.info("[pipeline] Skipped enrichment for %s throttled URL(s)", skipped)
        return jobs

    logger.info("[pipeline] Enriching %s job(s) with sparse snippets...", len(sparse))
    if skipped:
        logger.info("[pipeline] Skipped enrichment for %s throttled URL(s)", skipped)

    def _fetch_one(job: dict) -> tuple[str, dict | None]:
        logger.info("  enriching: %s @ %s", job["title"][:50], job["company"])
        try:
            full = fetcher(job["url"], use_llm=False)
            if full and full.get("snippet"):
                logger.info("    -> %s chars", len(full["snippet"]))
                return job["url"], {**job, "snippet": full["snippet"]}
        except Exception as e:
            logger.warning("    -> enrichment failed (%s), keeping original snippet", e)
            return job["url"], None
        logger.warning("    -> enrichment failed, keeping original snippet")
        return job["url"], None

    enriched: dict[str, dict] = {}
    with timed_stage(logger, "jd_enrichment", jobs=len(sparse), max_workers=max_workers):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for url, enriched_job in executor.map(_fetch_one, sparse):
                if enriched_job is not None:
                    enriched[url] = enriched_job

    return [enriched.get(job["url"], job) for job in jobs]


def drop_dead_urls_before_enrichment(
    jobs: list[dict],
    api_cfg: dict,
    *,
    url_checker: Callable[[str, int], bool] = url_is_alive,
) -> list[dict]:
    """Avoid fetching full JDs for postings that already fail URL verification."""
    url_cfg = api_cfg.get("http", {}).get("url_verification", {})
    if not url_cfg.get("enabled", True):
        return jobs

    timeout = int(url_cfg.get("timeout_seconds", 5))
    max_workers = int(url_cfg.get("max_workers") or api_cfg.get("llm", {}).get("max_workers", 5))

    def _check_job(job: dict) -> tuple[bool, dict]:
        url = job.get("url", "")
        if url and not url_checker(url, timeout):
            logger.info(
                "[pipeline] Skipping dead URL before enrichment: %s @ %s",
                job.get("title", "?")[:50],
                job.get("company", "?"),
            )
            return False, job
        return True, job

    with timed_stage(logger, "url_precheck", jobs=len(jobs), max_workers=max_workers):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            checked = list(executor.map(_check_job, jobs))

    alive = [job for ok, job in checked if ok]
    rejected = len(checked) - len(alive)

    if rejected:
        logger.info("[pipeline] Dropped %s dead URL(s) before enrichment", rejected)
    return alive
