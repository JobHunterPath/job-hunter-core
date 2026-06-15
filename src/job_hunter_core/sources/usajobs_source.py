"""USAJOBS — US federal government job board.

Free API key required. Register at https://developer.usajobs.gov/
Set USAJOBS_API_KEY and USAJOBS_USER_AGENT (your registered email) in environment.
Only fires for regions with country code US.
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter
from job_hunter_core.sources.source_config import source_page_cap

logger = logging.getLogger(__name__)

_API_URL = "https://data.usajobs.gov/api/search"
_PAGE_SIZE = 25


def _get_usajobs_creds() -> tuple[str, str]:
    """Return (api_key, user_agent) from config secrets."""
    secrets = load_api_config().get("secrets", {}).get("usajobs", {}) or {}
    import os

    api_key = os.environ.get(secrets.get("api_key_env_var", "USAJOBS_API_KEY"), "")
    user_agent = os.environ.get(secrets.get("user_agent_env_var", "USAJOBS_USER_AGENT"), "")
    return api_key, user_agent


class USAJobsSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "usajobs"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("usajobs", {}) or {}
        api_key, _ = _get_usajobs_creds()
        return bool(cfg.get("enabled", True)) and bool(api_key)

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch US federal jobs from USAJOBS API."""
        source_cfg = (
            load_api_config().get("http", {}).get("job_boards", {}).get("usajobs", {}) or {}
        )
        if not source_cfg.get("enabled", True):
            return []

        api_key, user_agent = _get_usajobs_creds()
        if not api_key or not user_agent:
            logger.debug("[usajobs] USAJOBS_API_KEY or USAJOBS_USER_AGENT not set — skipping")
            return []

        us_regions = {
            name: rc
            for name, rc in enabled_regions.items()
            if str(rc.get("country") or "").upper() == "US"
        }
        if not us_regions:
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = source_page_cap()
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        headers = {
            "Authorization-Key": api_key,
            "User-Agent": user_agent,
            "Host": "data.usajobs.gov",
        }
        jobs: list[JobPosting] = []

        for region_name, region_cfg in us_regions.items():
            location = str(region_cfg.get("location") or "")

            for title in title_filters:
                for page in range(1, max_pages + 1):
                    params: dict = {
                        "Keyword": title,
                        "ResultsPerPage": _PAGE_SIZE,
                        "Page": page,
                    }
                    if location:
                        params["LocationName"] = location

                    logger.info("[usajobs] [%s] p%d searching %r", region_name, page, title)
                    try:
                        resp = requests.get(
                            _API_URL, headers=headers, params=params, timeout=timeout
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        logger.warning(
                            "[usajobs] request failed for %r in %s: %s", title, region_name, exc
                        )
                        break

                    items = data.get("SearchResult", {}).get("SearchResultItems", []) or []
                    if not items:
                        break

                    before = len(jobs)
                    for item in items:
                        descriptor = item.get("MatchedObjectDescriptor", {}) or {}
                        job_title = str(descriptor.get("PositionTitle") or "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue
                        loc_display = str(
                            descriptor.get("PositionLocationDisplay") or location or "USA"
                        )
                        snippet = strip_html(
                            str(
                                (descriptor.get("UserArea", {}) or {})
                                .get("Details", {})
                                .get("JobSummary")
                                or ""
                            )
                        )
                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=str(descriptor.get("OrganizationName") or "US Government"),
                                url=str(descriptor.get("PositionURI") or ""),
                                posted=str(descriptor.get("PublicationStartDate") or "")[:10],
                                location=loc_display,
                                snippet=snippet[:3000],
                                source="USAJOBS",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[usajobs] +%d jobs for %r in %s (p%d)",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )

                    if len(items) < _PAGE_SIZE:
                        break

        logger.info("[usajobs] Complete: %d total jobs found", len(jobs))
        return jobs
