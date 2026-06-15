"""Working Nomads remote job board — no API key required.

Public REST endpoint returns all current remote jobs as a JSON list.
No geographic restriction; fires for all enabled regions.
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


class WorkingNomadsSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "workingnomads"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("workingnomads", {}) or {}
        return bool(cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch remote jobs from Working Nomads public API."""
        source_cfg = (
            load_api_config().get("http", {}).get("job_boards", {}).get("workingnomads", {}) or {}
        )
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )

        logger.info("[workingnomads] Fetching all remote jobs")
        try:
            resp = requests.get(_API_URL, timeout=timeout)
            resp.raise_for_status()
            raw_jobs = resp.json()
        except Exception as exc:
            logger.warning("[workingnomads] request failed: %s", exc)
            return []

        if not isinstance(raw_jobs, list):
            logger.warning("[workingnomads] unexpected response type: %s", type(raw_jobs))
            return []

        region_name = next(iter(enabled_regions), "remote")
        jobs: list[JobPosting] = []
        for item in raw_jobs:
            if not isinstance(item, dict):
                continue
            job_title = str(item.get("title") or "")
            if not title_matches(job_title, title_filters, _excluded):
                continue
            jobs.append(
                JobPosting(
                    title=job_title,
                    company=str(item.get("company_name") or ""),
                    url=str(item.get("url") or ""),
                    posted=str(item.get("pub_date") or "")[:10],
                    location=str(item.get("region") or "Remote"),
                    snippet=strip_html(str(item.get("description") or ""))[:3000],
                    source="WorkingNomads",
                    query=f"{' | '.join(title_filters[:3])} @ {region_name}",
                    region=region_name,
                )
            )

        logger.info("[workingnomads] Complete: %d jobs matched title filters", len(jobs))
        return jobs
