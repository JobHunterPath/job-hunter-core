"""Adzuna job board source — free official API with global coverage.

Supports: AU, AT, BE, BR, CA, DE, ES, FR, GB, IT, MX, NL, NZ, PL, SG, US, ZA, CH, IN.
Register for a free API key at https://developer.adzuna.com/

The Adzuna country is derived automatically from each region's ISO country code
(the `country` field in search_config.yml regions). No mapping config needed.

Required env vars (both optional — source skips silently if absent):
  ADZUNA_APP_ID   — application ID from developer.adzuna.com
  ADZUNA_API_KEY  — API key from developer.adzuna.com
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
from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import title_matches

logger = logging.getLogger(__name__)

_TIMEOUT = get_timeout("job_boards")
_BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

# ISO 3166-1 alpha-2 → Adzuna country code (only supported countries listed)
_ISO_TO_ADZUNA: dict[str, str] = {
    "AU": "au",
    "AT": "at",
    "BE": "be",
    "BR": "br",
    "CA": "ca",
    "DE": "de",
    "ES": "es",
    "FR": "fr",
    "GB": "gb",
    "IE": "gb",  # Adzuna gb covers Ireland
    "IN": "in",
    "IT": "it",
    "MX": "mx",
    "NL": "nl",
    "NZ": "nz",
    "PL": "pl",
    "SG": "sg",
    "CH": "ch",
    "US": "us",
    "ZA": "za",
}


def _parse_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def fetch_adzuna_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
    app_id: str,
    api_key: str,
) -> list[dict]:
    """
    Fetch jobs from Adzuna for each enabled region whose ISO country code is supported.
    Returns [] silently if credentials are missing or adzuna is disabled.
    """
    if not app_id or not api_key:
        logger.warning("[adzuna] ADZUNA_APP_ID or ADZUNA_API_KEY not set — skipping")
        return []

    adzuna_cfg = (
        load_api_config().get("http", {}).get("job_boards", {}).get("adzuna", {}) or {}
    )
    if not adzuna_cfg.get("enabled", False):
        return []

    results_per_page = int(adzuna_cfg.get("results_per_page", 50))
    excluded_title_terms: list[str] = (
        config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    )

    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        iso = region_config.get("country", "").upper()
        country = _ISO_TO_ADZUNA.get(iso, "")
        if not country:
            continue

        location = region_config.get("location", "")

        for title in title_filters:
            logger.info("[adzuna] [%s] Searching country=%r for %r", region_name, country, title)
            params: dict = {
                "app_id": app_id,
                "app_key": api_key,
                "what": title,
                "results_per_page": results_per_page,
                "content-type": "application/json",
            }
            if location:
                params["where"] = location

            url = _BASE_URL.format(country=country, page=1)
            if not reserve_api_call("adzuna"):
                continue

            try:
                resp = requests.get(url, params=params, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json().get("results", [])
            except Exception as exc:
                if is_api_quota_exhausted(exc):
                    mark_api_exhausted("adzuna", exc=exc)
                    return jobs
                logger.warning("[adzuna] request failed for %r in %r: %s", title, region_name, exc)
                continue

            region_term = location.lower().replace("remote ", "").replace(" remote", "").strip()

            before = len(jobs)
            for item in data:
                job_title = item.get("title", "")
                if not title_matches(job_title, title_filters, excluded_title_terms):
                    continue

                location_str = item.get("location", {}).get("display_name", "")
                if location_str and "remote" not in location_str.lower():
                    if region_term and region_term not in location_str.lower():
                        continue
                description = (item.get("description") or "")[:1000]
                snippet = f"{location_str} — {description}" if location_str else description

                jobs.append(
                    {
                        "title": job_title,
                        "company": item.get("company", {}).get("display_name", ""),
                        "url": item.get("redirect_url", ""),
                        "posted": _parse_date(item.get("created")),
                        "snippet": snippet,
                        "source": "Adzuna",
                    }
                )

            logger.info("[adzuna] +%d jobs for %r in %r", len(jobs) - before, title, region_name)

    logger.info("[adzuna] Complete: %d total jobs found", len(jobs))
    return jobs
