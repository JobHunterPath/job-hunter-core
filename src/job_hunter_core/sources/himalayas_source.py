"""Free Himalayas remote jobs API source."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import location_matches, strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://himalayas.app/jobs/api/search"


def _posted(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
    if isinstance(value, str):
        return value[:10]
    return ""


def _country_matches(job: dict[str, Any], iso: str) -> bool:
    if not iso:
        return True
    restrictions = job.get("locationRestrictions") or []
    if not restrictions:
        return True
    return any(
        str(item.get("alpha2") or "").upper() == iso
        for item in restrictions
        if isinstance(item, dict)
    )


def _location_text(job: dict[str, Any]) -> str:
    restrictions = job.get("locationRestrictions") or []
    names = [
        str(item.get("name") or "").strip()
        for item in restrictions
        if isinstance(item, dict) and item.get("name")
    ]
    return ", ".join(names) if names else "Remote"


class HimalayasSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "himalayas"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("himalayas", {}) or {}
        return bool(source_cfg.get("enabled", False))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict[str, Any],
        config: dict[str, Any],
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch remote jobs from Himalayas' no-auth public API."""
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("himalayas", {}) or {}
        if not source_cfg.get("enabled", False):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        max_pages = int(source_cfg.get("max_pages_per_query", 1))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            iso = str(region_config.get("country") or "").upper()
            location = str(region_config.get("location") or "")
            for title in title_filters:
                for page in range(1, max_pages + 1):
                    try:
                        resp = requests.get(
                            _SEARCH_URL,
                            params={"q": title, "country": iso, "sort": "recent", "page": page},
                            timeout=timeout,
                        )
                        resp.raise_for_status()
                        raw_jobs = resp.json().get("jobs", [])
                    except Exception as exc:
                        logger.warning(
                            "[himalayas] failed for %r in %s page %s: %s", title, region_name, page, exc
                        )
                        break

                    if not raw_jobs:
                        break

                    before = len(jobs)
                    for item in raw_jobs:
                        job_title = str(item.get("title") or "")
                        job_location = _location_text(item)
                        if not title_matches(job_title, title_filters, _excluded):
                            continue
                        if not _country_matches(item, iso):
                            continue
                        if (
                            location
                            and job_location != "Remote"
                            and not location_matches(job_location, location)
                        ):
                            continue
                        description = strip_html(item.get("description") or item.get("excerpt") or "")
                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=str(item.get("companyName") or ""),
                                url=str(item.get("applicationLink") or item.get("guid") or ""),
                                posted=_posted(item.get("pubDate")),
                                location=job_location,
                                snippet=description[:3000],
                                source="Himalayas",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[himalayas] +%d jobs for %r in %s", len(jobs) - before, title, region_name
                    )

        return jobs


def fetch_himalayas_jobs(
    title_filters: list[str],
    enabled_regions: dict[str, Any],
    config: dict[str, Any],
) -> list[dict]:
    """Fetch remote jobs from Himalayas' no-auth public API."""
    return [j.to_dict() for j in HimalayasSource().fetch(title_filters, enabled_regions, config)]
