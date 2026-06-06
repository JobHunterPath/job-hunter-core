"""Jobicy remote jobs API source — no key required.

Free public API: https://jobicy.com/jobs-rss-feed
Up to 100 results per request. Supports geo (ISO 3166-1 alpha-2) and tag filters.
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.api_budget import reserve_api_call
from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches

logger = logging.getLogger(__name__)

_API_URL = "https://jobicy.com/api/v2/remote-jobs"


def fetch_jobicy_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch remote jobs from Jobicy's free public API."""
    source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobicy", {}) or {}
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        iso = region_config.get("country", "").lower()

        for title in title_filters:
            if not reserve_api_call("jobicy"):
                continue

            params: dict = {"count": 100, "tag": title}
            if iso:
                params["geo"] = iso

            logger.info("[jobicy] [%s] Searching for %r (geo=%r)", region_name, title, iso or "any")

            try:
                resp = requests.get(_API_URL, params=params, timeout=timeout)
                resp.raise_for_status()
                raw_jobs = resp.json().get("jobs", [])
            except Exception as exc:
                logger.warning("[jobicy] request failed for %r in %s: %s", title, region_name, exc)
                continue

            if not isinstance(raw_jobs, list):
                continue

            before = len(jobs)
            for item in raw_jobs:
                if not isinstance(item, dict):
                    continue
                job_title = str(item.get("jobTitle") or "")
                if not title_matches(job_title, title_filters, excluded_title_terms):
                    continue
                description = strip_html(str(item.get("jobDescription") or ""))
                jobs.append(
                    {
                        "title": job_title,
                        "company": str(item.get("companyName") or ""),
                        "url": str(item.get("url") or ""),
                        "posted": str(item.get("pubDate") or "")[:10],
                        "location": str(item.get("jobGeo") or "Remote"),
                        "snippet": description[:3000],
                        "source": "Jobicy",
                        "query": f"{title} @ {region_name}",
                        "region": region_name,
                    }
                )
            logger.info("[jobicy] +%d jobs for %r in %s", len(jobs) - before, title, region_name)

    logger.info("[jobicy] Complete: %d total jobs found", len(jobs))
    return jobs
