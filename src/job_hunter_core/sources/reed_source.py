"""Reed.co.uk job board source — free official API for UK and Ireland.

Register for a free API key at https://www.reed.co.uk/developers/jobseeker

Reed is activated automatically for any region with country: "GB" or country: "IE"
in search_config.yml. No additional mapping config is needed.

Required env var (optional — source skips silently if absent):
  REED_API_KEY — API key from reed.co.uk/developers
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

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

_TIMEOUT = get_timeout("job_boards")
_SEARCH_URL = "https://www.reed.co.uk/api/1.0/search"
_REED_COUNTRIES: frozenset[str] = frozenset({"GB", "IE"})


def _parse_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


class ReedSource(JobSourceAdapter):
    def __init__(self) -> None:
        self._api_key: str = os.environ.get("REED_API_KEY", "")

    @property
    def name(self) -> str:
        return "reed"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        if not self._api_key:
            return False
        cfg = load_api_config().get("http", {}).get("job_boards", {}).get("reed", {}) or {}
        return bool(cfg.get("enabled", False))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """
        Fetch jobs from Reed.co.uk for any region with country GB or IE.
        Returns [] silently if the API key is missing or reed is disabled.
        """
        if not self._api_key:
            logger.warning("[reed] REED_API_KEY not set — skipping")
            return []

        reed_cfg = (
            load_api_config().get("http", {}).get("job_boards", {}).get("reed", {}) or {}
        )
        if not reed_cfg.get("enabled", False):
            return []

        results_wanted = int(reed_cfg.get("results_wanted", 50))
        max_pages = int(reed_cfg.get("max_pages_per_query", 1))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )

        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            if region_config.get("country", "").upper() not in _REED_COUNTRIES:
                continue

            location = region_config.get("location", "")

            for title in title_filters:
                logger.info("[reed] [%s] Searching for %r", region_name, title)
                base_params: dict = {"keywords": title, "resultsToTake": results_wanted}
                if location:
                    base_params["locationName"] = location
                    base_params["distancefromLocation"] = 15

                for page in range(1, max_pages + 1):
                    if not reserve_api_call("reed"):
                        break

                    params = {**base_params, "resultsToSkip": (page - 1) * results_wanted}
                    try:
                        resp = requests.get(
                            _SEARCH_URL,
                            params=params,
                            auth=(self._api_key, ""),
                            timeout=_TIMEOUT,
                        )
                        resp.raise_for_status()
                        data = resp.json().get("results", [])
                    except Exception as exc:
                        if is_api_quota_exhausted(exc):
                            mark_api_exhausted("reed", exc=exc)
                            return jobs
                        logger.warning(
                            "[reed] request failed for %r in %r page %s: %s",
                            title,
                            region_name,
                            page,
                            exc,
                        )
                        break

                    if not data:
                        break

                    before = len(jobs)
                    for item in data:
                        job_title = item.get("jobTitle", "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue

                        location_str = item.get("locationName", "")
                        description = (item.get("jobDescription") or "")[:1000]
                        snippet = (
                            f"{location_str} — {description}" if location_str else description
                        )

                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=item.get("employerName", ""),
                                url=item.get("jobUrl", ""),
                                posted=_parse_date(item.get("date")),
                                location=location_str,
                                snippet=snippet,
                                source="Reed",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )

                    logger.info(
                        "[reed] +%d jobs for %r in %r page %s",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )
                    if len(data) < results_wanted:
                        break

        logger.info("[reed] Complete: %d total jobs found", len(jobs))
        return jobs
