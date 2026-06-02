"""Reed.co.uk job board source — free official API for UK and Ireland.

Register for a free API key at https://www.reed.co.uk/developers/jobseeker

Reed is activated automatically for any region with country: "GB" or country: "IE"
in search_config.yml. No additional mapping config is needed.

Required env var (optional — source skips silently if absent):
  REED_API_KEY — API key from reed.co.uk/developers
"""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from job_hunter_core.core.api_budget import (
    is_api_quota_exhausted,
    mark_api_exhausted,
    reserve_api_call,
)
from job_hunter_core.core.config import get_timeout
from job_hunter_core.core.utils import title_matches

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


def fetch_reed_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
    api_key: str,
) -> list[dict]:
    """
    Fetch jobs from Reed.co.uk for any region with country GB or IE.
    Returns [] silently if the API key is missing or reed is disabled.
    """
    if not api_key:
        logger.warning("[reed] REED_API_KEY not set — skipping")
        return []

    reed_cfg = config.get("job_boards", {}).get("reed", {}) or {}
    if not reed_cfg.get("enabled", False):
        return []

    results_wanted = int(reed_cfg.get("results_wanted", 50))
    excluded_title_terms: list[str] = (
        config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    )

    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        if region_config.get("country", "").upper() not in _REED_COUNTRIES:
            continue

        location = region_config.get("location", "")

        for title in title_filters:
            logger.info("[reed] [%s] Searching for %r", region_name, title)
            params: dict = {
                "keywords": title,
                "resultsToTake": results_wanted,
            }
            if location:
                params["locationName"] = location
                params["distancefromLocation"] = 15

            if not reserve_api_call("reed"):
                continue

            try:
                resp = requests.get(
                    _SEARCH_URL,
                    params=params,
                    auth=(api_key, ""),
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json().get("results", [])
            except Exception as exc:
                if is_api_quota_exhausted(exc):
                    mark_api_exhausted("reed", exc=exc)
                    return jobs
                logger.warning("[reed] request failed for %r in %r: %s", title, region_name, exc)
                continue

            before = len(jobs)
            for item in data:
                job_title = item.get("jobTitle", "")
                if not title_matches(job_title, title_filters, excluded_title_terms):
                    continue

                location_str = item.get("locationName", "")
                description = (item.get("jobDescription") or "")[:1000]
                snippet = f"{location_str} — {description}" if location_str else description

                jobs.append(
                    {
                        "title": job_title,
                        "company": item.get("employerName", ""),
                        "url": item.get("jobUrl", ""),
                        "posted": _parse_date(item.get("date")),
                        "snippet": snippet,
                        "source": "Reed",
                    }
                )

            logger.info("[reed] +%d jobs for %r in %r", len(jobs) - before, title, region_name)

    logger.info("[reed] Complete: %d total jobs found", len(jobs))
    return jobs
