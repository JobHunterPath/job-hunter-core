"""Free Bundesagentur fuer Arbeit Jobsuche source for German regions."""

from __future__ import annotations

import logging
from typing import Any

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import location_matches, title_matches

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs"
_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{0}"


def _location(item: dict[str, Any]) -> str:
    place = item.get("arbeitsort") or {}
    if isinstance(place, dict):
        return ", ".join(
            str(place.get(key) or "").strip() for key in ("ort", "land") if place.get(key)
        )
    return ""


def fetch_arbeitsagentur_jobs(
    title_filters: list[str],
    enabled_regions: dict[str, Any],
    config: dict[str, Any],
) -> list[dict]:
    """Fetch German public employment-agency jobs for DE regions."""
    source_cfg = (
        load_api_config().get("http", {}).get("job_boards", {}).get("arbeitsagentur", {}) or {}
    )
    if not source_cfg.get("enabled", False):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    size = int(source_cfg.get("results_per_query", 25))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        if str(region_config.get("country") or "").upper() != "DE":
            continue
        location = str(region_config.get("location") or "")
        for title in title_filters:
            try:
                resp = requests.get(
                    _SEARCH_URL,
                    params={"was": title, "wo": location, "page": 1, "size": size},
                    headers={"X-API-Key": "jobboerse-jobsuche"},
                    timeout=timeout,
                )
                resp.raise_for_status()
                postings = resp.json().get("stellenangebote", [])
            except Exception as exc:
                logger.warning("[arbeitsagentur] failed for %r in %s: %s", title, region_name, exc)
                continue

            before = len(jobs)
            for item in postings:
                job_title = str(item.get("titel") or "")
                job_location = _location(item)
                if not title_matches(job_title, title_filters, excluded_title_terms):
                    continue
                if location and job_location and not location_matches(job_location, location):
                    continue
                ref = str(item.get("refnr") or item.get("hashId") or "")
                jobs.append(
                    {
                        "title": job_title,
                        "company": str(item.get("arbeitgeber") or ""),
                        "url": _DETAIL_URL.format(ref) if ref else "",
                        "posted": str(item.get("aktuelleVeroeffentlichungsdatum") or "")[:10],
                        "location": job_location,
                        "snippet": str(item.get("stellenbeschreibung") or item.get("beruf") or "")[
                            :3000
                        ],
                        "source": "Arbeitsagentur",
                        "query": f"{title} @ {region_name}",
                        "region": region_name,
                    }
                )
            logger.info(
                "[arbeitsagentur] +%d jobs for %r in %s", len(jobs) - before, title, region_name
            )

    return jobs
