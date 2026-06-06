"""RemoteOK job feed source — no key required.

Public JSON feed: https://remoteok.com/api
Returns all remote jobs; first element is metadata — skip it.
Filter locally by title and region location.
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import location_matches, strip_html, title_matches

logger = logging.getLogger(__name__)

_API_URL = "https://remoteok.com/api"
_HEADERS = {"User-Agent": "job-hunter/1.0"}


def fetch_remoteok_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch remote jobs from RemoteOK's public JSON feed."""
    source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("remoteok", {}) or {}
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []

    logger.info("[remoteok] Fetching job feed")
    try:
        resp = requests.get(_API_URL, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as exc:
        logger.warning("[remoteok] request failed: %s", exc)
        return []

    if not isinstance(raw, list) or len(raw) < 2:
        return []

    # First element is legal/metadata dict — skip it
    items = raw[1:]

    region_locations = [
        rc.get("location", "")
        for rc in enabled_regions.values()
        if rc.get("location")
    ]
    first_region = next(iter(enabled_regions), "")

    jobs: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        job_title = str(item.get("position") or "")
        if not title_matches(job_title, title_filters, excluded_title_terms):
            continue
        job_location = str(item.get("location") or "Remote")
        # Accept worldwide/remote postings; otherwise check against region locations
        if (
            region_locations
            and job_location
            and job_location.lower() not in ("", "remote", "worldwide", "anywhere")
        ):
            if not any(location_matches(job_location, loc) for loc in region_locations):
                continue
        tags = item.get("tags") or []
        description = strip_html(str(item.get("description") or ""))
        snippet = description or ", ".join(str(t) for t in tags)
        jobs.append(
            {
                "title": job_title,
                "company": str(item.get("company") or ""),
                "url": str(item.get("url") or ""),
                "posted": str(item.get("date") or "")[:10],
                "location": job_location,
                "snippet": snippet[:3000],
                "source": "RemoteOK",
                "query": job_title,
                "region": first_region,
            }
        )

    logger.info("[remoteok] %d jobs matched after filtering", len(jobs))
    return jobs
