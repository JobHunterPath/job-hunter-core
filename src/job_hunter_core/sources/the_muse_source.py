"""Free The Muse jobs API source."""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import location_matches, strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_API_URL = "https://www.themuse.com/api/public/jobs"


class TheMuseSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "the_muse"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("the_muse", {}) or {}
        return bool(source_cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from The Muse's free public API."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("the_muse", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = int(source_cfg.get("max_pages_per_query", 1))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []

        query_label = ", ".join(title_filters)
        for region_name, region_config in enabled_regions.items():
            location = str(region_config.get("location") or "")
            for page in range(0, max_pages):
                try:
                    resp = requests.get(
                        _API_URL,
                        params={"page": page, "descending": "true"},
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    raw_jobs = resp.json().get("results", [])
                except Exception as exc:
                    logger.warning(
                        "[the-muse] failed for %r in %s page %s: %s",
                        query_label,
                        region_name,
                        page,
                        exc,
                    )
                    break

                if not raw_jobs:
                    break

                before = len(jobs)
                for item in raw_jobs:
                    job_title = str(item.get("name") or "")
                    job_location_list = item.get("locations") or []
                    job_location = (
                        ", ".join(
                            str(loc.get("name") or "")
                            for loc in job_location_list
                            if isinstance(loc, dict)
                        )
                        or "Remote"
                    )
                    if not title_matches(job_title, title_filters, _excluded):
                        continue
                    if location and job_location != "Remote":
                        if not location_matches(job_location, location):
                            continue
                    description = strip_html(item.get("contents") or "")
                    company_name = str((item.get("company") or {}).get("name") or "")
                    job_url = str(item.get("refs", {}).get("landing_page") or "")
                    posted = str(item.get("publication_date") or "")[:10]
                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=company_name,
                            url=job_url,
                            posted=posted,
                            location=job_location,
                            snippet=description[:3000],
                            source="The Muse",
                            query=f"{query_label} @ {region_name}",
                            region=region_name,
                        )
                    )
                logger.info(
                    "[the-muse] +%d jobs for %r in %s", len(jobs) - before, query_label, region_name
                )

        return jobs


def fetch_the_muse_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch jobs from The Muse's free public API."""
    return [j.to_dict() for j in TheMuseSource().fetch(title_filters, enabled_regions, config)]
