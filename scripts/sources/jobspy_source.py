"""JobSpy-based job discovery via Indeed and Google Jobs.

Falls back gracefully if python-jobspy is not installed — the rest of
the pipeline continues without it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _str(val: Any) -> str:
    """Safe string conversion — handles None and float NaN from pandas."""
    if val is None or val != val:  # val != val is True only for NaN
        return ""
    return str(val).strip()


def _row_to_job(row: Any, region_name: str) -> dict | None:
    title = _str(row.get("title"))
    url = _str(row.get("job_url"))
    if not title or not url:
        return None

    site = _str(row.get("site")).lower()
    return {
        "title": title,
        "company": _str(row.get("company")),
        "url": url,
        "posted": _str(row.get("date_posted")),
        "snippet": _str(row.get("description"))[:3000],
        "source": f"JobSpy/{site.title()}" if site else "JobSpy",
        "query": f"{title} @ {region_name}",
    }


def fetch_jobspy_jobs(
    title_filters: list[str],
    enabled_regions: dict[str, Any],
    config: dict[str, Any],
) -> list[dict]:
    """
    Scrape Indeed and Google Jobs via python-jobspy for each title × region.
    Returns jobs in the standard pipeline format.
    Silently skips if python-jobspy is not installed or disabled in config.
    """
    try:
        from jobspy import scrape_jobs  # type: ignore[import]
    except ImportError:
        logger.warning("[jobspy] python-jobspy not installed — skipping JobSpy discovery")
        return []

    jobspy_cfg = config.get("jobspy", {}) or {}
    if not jobspy_cfg.get("enabled", False):
        return []

    hours_old = int(jobspy_cfg.get("hours_old", 72))
    results_per_query = int(jobspy_cfg.get("results_per_query", 15))
    country_map: dict[str, str] = jobspy_cfg.get("country_indeed_by_region", {}) or {}

    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        location = region_config.get("location", "")
        country_indeed = country_map.get(region_name, "")

        # Always include Google Jobs; add Indeed only when a country code is configured.
        sources = ["google"]
        if country_indeed:
            sources.append("indeed")

        for title in title_filters:
            logger.info("[jobspy] [%s] Searching %s for %r", region_name, sources, title)
            try:
                df = scrape_jobs(
                    site_name=sources,
                    search_term=title,
                    location=location,
                    results_wanted=results_per_query,
                    hours_old=hours_old,
                    country_indeed=country_indeed or "usa",
                    description_format="markdown",
                    verbose=0,
                )
            except Exception as exc:
                logger.warning("[jobspy] scrape_jobs failed for %r in %r: %s", title, location, exc)
                continue

            if df is None or df.empty:
                logger.info("[jobspy] No results for %r in %r", title, location)
                continue

            before = len(jobs)
            for _, row in df.iterrows():
                job = _row_to_job(row, region_name)
                if job:
                    jobs.append(job)
            logger.info("[jobspy] +%d jobs for %r in %r", len(jobs) - before, title, location)

    logger.info("[jobspy] Complete: %d total jobs found", len(jobs))
    return jobs
