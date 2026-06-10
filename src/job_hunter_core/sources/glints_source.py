"""Glints — Southeast Asia job board (SG, ID, MY, VN, PH).

Unofficial REST-like JSON API. No auth required.
Only fires for SEA regions (SG, ID, MY, VN, PH).
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_API_URL = "https://glints.com/api/jobs"
_JOB_BASE = "https://glints.com/opportunities/jobs"
_PAGE_SIZE = 30

_SEA_CODES: frozenset[str] = frozenset({"SG", "ID", "MY", "VN", "PH"})

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://glints.com/",
}


class GlintsSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "glints"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("glints", {}) or {}
        return bool(source_cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from Glints for SEA regions.

        Only runs for regions whose country code is in SG, ID, MY, VN, PH.
        """
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("glints", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            iso = region_config.get("country", "").upper()
            if iso not in _SEA_CODES:
                continue

            for title in title_filters:
                page = 1
                while True:
                    try:
                        resp = requests.get(
                            _API_URL,
                            params={
                                "query": title,
                                "countryCode": iso,
                                "page": page,
                                "pageSize": _PAGE_SIZE,
                            },
                            headers=_HEADERS,
                            timeout=timeout,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        logger.warning(
                            "[glints] failed for %r in %s page %d: %s",
                            title,
                            region_name,
                            page,
                            exc,
                        )
                        break

                    # Glints nests data under various keys depending on version
                    items = (
                        (data.get("data") or {}).get("jobs")
                        or data.get("jobs")
                        or data.get("data")
                        or []
                    )
                    if isinstance(items, dict):
                        items = items.get("data") or []
                    if not items:
                        break

                    before = len(jobs)
                    for item in items:
                        job_title = str(item.get("title") or item.get("name") or "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue

                        company_obj = item.get("company") or item.get("organisation") or {}
                        company = str(company_obj.get("name") or "")
                        job_id = str(item.get("id") or item.get("uuid") or "")
                        job_url = f"{_JOB_BASE}/{job_id}" if job_id else ""

                        city_obj = item.get("city") or {}
                        country_obj = item.get("country") or {}
                        city = str(
                            city_obj.get("name") if isinstance(city_obj, dict) else city_obj or ""
                        )
                        country_name = str(
                            country_obj.get("name")
                            if isinstance(country_obj, dict)
                            else country_obj or iso
                        )
                        job_location = ", ".join(filter(None, [city, country_name]))

                        created_at = str(item.get("createdAt") or item.get("created_at") or "")[:10]
                        description = strip_html(str(item.get("description") or ""))

                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=company,
                                url=job_url,
                                posted=created_at,
                                location=job_location,
                                snippet=description[:3000],
                                source="Glints",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[glints] +%d jobs for %r in %s page %d",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )

                    if len(items) < _PAGE_SIZE:
                        break
                    page += 1

        logger.info("[glints] Complete: %d total jobs", len(jobs))
        return jobs


def fetch_glints_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch jobs from Glints for SEA regions.

    Only runs for regions whose country code is in SG, ID, MY, VN, PH.
    """
    return [j.to_dict() for j in GlintsSource().fetch(title_filters, enabled_regions, config)]
