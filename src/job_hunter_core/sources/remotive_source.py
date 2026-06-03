"""Free Remotive remote jobs API source."""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches

logger = logging.getLogger(__name__)

_API_URL = "https://remotive.com/api/remote-jobs"


def fetch_remotive_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch remote jobs from Remotive's free public API."""
    source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("remotive", {}) or {}
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    max_pages = int(source_cfg.get("max_pages_per_query", 1))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        location = str(region_config.get("location") or "")
        for title in title_filters:
            for page in range(1, max_pages + 1):
                try:
                    resp = requests.get(
                        _API_URL,
                        params={"search": title, "limit": 100, "page": page},
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    raw_jobs = resp.json().get("jobs", [])
                except Exception as exc:
                    logger.warning(
                        "[remotive] failed for %r in %s page %s: %s",
                        title,
                        region_name,
                        page,
                        exc,
                    )
                    break

                if not raw_jobs:
                    break

                before = len(jobs)
                for item in raw_jobs:
                    job_title = str(item.get("title") or "")
                    job_location = str(item.get("candidate_required_location") or "Remote")
                    if not title_matches(job_title, title_filters, excluded_title_terms):
                        continue
                    description = strip_html(item.get("description") or "")
                    jobs.append(
                        {
                            "title": job_title,
                            "company": str(item.get("company_name") or ""),
                            "url": str(item.get("url") or ""),
                            "posted": str(item.get("publication_date") or "")[:10],
                            "location": job_location,
                            "snippet": description[:3000],
                            "source": "Remotive",
                            "query": f"{title} @ {region_name}",
                            "region": region_name,
                        }
                    )
                logger.info(
                    "[remotive] +%d jobs for %r in %s", len(jobs) - before, title, region_name
                )

    return jobs
