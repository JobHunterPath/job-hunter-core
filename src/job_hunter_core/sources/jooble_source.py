"""Jooble job aggregator source — free API key required.

Register for a free key at https://jooble.org/api/about
POST-based paged search with keyword + location.

Required env var (optional — source skips silently if absent):
  JOOBLE_API_KEY — API key from jooble.org
"""

from __future__ import annotations

import logging
import os

import requests

from job_hunter_core.core.api_budget import (
    is_api_quota_exhausted,
    mark_api_exhausted,
    reserve_api_call,
)
from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://jooble.org/api/{api_key}"


class JoobleSource(JobSourceAdapter):
    def __init__(self) -> None:
        self._api_key: str = os.environ.get("JOOBLE_API_KEY", "")

    @property
    def name(self) -> str:
        return "jooble"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        if not self._api_key:
            return False
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jooble", {}) or {}
        return bool(cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from Jooble for each title × region. Returns [] silently if key is missing."""
        if not self._api_key:
            logger.warning("[jooble] JOOBLE_API_KEY not set — skipping")
            return []

        source_cfg = (
            load_api_config().get("http", {}).get("job_boards", {}).get("jooble", {}) or {}
        )
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = int(source_cfg.get("max_pages_per_query", 3))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )

        url = _BASE_URL.format(api_key=self._api_key)
        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            location = region_config.get("location", "")

            for title in title_filters:
                logger.info("[jooble] [%s] Searching for %r", region_name, title)

                for page in range(1, max_pages + 1):
                    if not reserve_api_call("jooble"):
                        return jobs

                    try:
                        resp = requests.post(
                            url,
                            json={"keywords": title, "location": location, "page": page},
                            timeout=timeout,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        if is_api_quota_exhausted(exc):
                            mark_api_exhausted("jooble", exc=exc)
                            return jobs
                        logger.warning(
                            "[jooble] request failed for %r in %r page %s: %s",
                            title,
                            region_name,
                            page,
                            exc,
                        )
                        break

                    raw_jobs = data.get("jobs") if isinstance(data, dict) else None
                    if not raw_jobs:
                        break

                    before = len(jobs)
                    for item in raw_jobs:
                        if not isinstance(item, dict):
                            continue
                        job_title = str(item.get("title") or "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue
                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=str(item.get("company") or ""),
                                url=str(item.get("link") or ""),
                                posted=str(item.get("updated") or "")[:10],
                                location=str(item.get("location") or ""),
                                snippet=str(item.get("snippet") or "")[:3000],
                                source="Jooble",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[jooble] +%d jobs for %r in %r page %s",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )

        logger.info("[jooble] Complete: %d total jobs found", len(jobs))
        return jobs
