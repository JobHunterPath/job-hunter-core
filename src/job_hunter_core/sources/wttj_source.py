"""Welcome to the Jungle (WTTJ) — global job board with strong EU/France coverage.

Free public JSON API, no auth required.
Fires for any enabled region (global board); no country guard needed.
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_API_URL = "https://api.welcometothejungle.com/api/v1/jobs"
_JOB_BASE = "https://www.welcometothejungle.com/en/companies"
_PAGE_SIZE = 30
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en",
}


class WTTJSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "wttj"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("wttj", {}) or {}
        return bool(source_cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from Welcome to the Jungle public API.

        Global board — fires for all enabled regions; uses aroundQuery for location filtering.
        """
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("wttj", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        for region_name, region_config in enabled_regions.items():
            location = region_config.get("location", "")

            for title in title_filters:
                page = 1
                while True:
                    params: dict = {
                        "query": title,
                        "page": page,
                        "per_page": _PAGE_SIZE,
                        "language": "en",
                    }
                    if location:
                        params["aroundQuery"] = location

                    try:
                        resp = requests.get(
                            _API_URL,
                            params=params,
                            headers=_HEADERS,
                            timeout=timeout,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        logger.warning(
                            "[wttj] failed for %r in %s page %d: %s",
                            title,
                            region_name,
                            page,
                            exc,
                        )
                        break

                    items = data.get("jobs") or []
                    if not items:
                        break

                    before = len(jobs)
                    for item in items:
                        job_id = str(item.get("id") or item.get("slug") or "")
                        if job_id in seen_ids:
                            continue
                        if job_id:
                            seen_ids.add(job_id)

                        job_title = str(item.get("name") or "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue

                        org = item.get("organization") or {}
                        company = str(org.get("name") or "")
                        org_slug = str(org.get("slug") or "")
                        job_slug = str(item.get("slug") or job_id)
                        job_url = (
                            f"{_JOB_BASE}/{org_slug}/jobs/{job_slug}"
                            if org_slug and job_slug
                            else ""
                        )

                        office = item.get("office") or {}
                        city = str(office.get("city") or "")
                        country_field = office.get("country") or {}
                        country = str(
                            country_field.get("code", "")
                            if isinstance(country_field, dict)
                            else country_field
                        )
                        job_location = ", ".join(filter(None, [city, country]))

                        published_at = str(item.get("published_at") or "")[:10]
                        description = strip_html(str(item.get("description") or ""))

                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=company,
                                url=job_url,
                                posted=published_at,
                                location=job_location or location,
                                snippet=description[:3000],
                                source="Welcome to the Jungle",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[wttj] +%d jobs for %r in %s page %d",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )

                    if len(items) < _PAGE_SIZE:
                        break
                    page += 1

        logger.info("[wttj] Complete: %d total jobs", len(jobs))
        return jobs
