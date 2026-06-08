"""
Global job board scrapers: Arbeitnow and JSearch (RapidAPI).

These search across the whole market rather than targeting specific career pages,
so they complement the per-company ATS fetchers in sources/ats.py.

- Arbeitnow: free, no auth, Germany-focused REST API.
- JSearch:   RapidAPI aggregator (LinkedIn, Indeed, Glassdoor, etc.);
             free tier = 200 req/month; requires RAPIDAPI_KEY.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests

from job_hunter_core.core.api_budget import (
    is_api_quota_exhausted,
    mark_api_exhausted,
    reserve_api_call,
)
from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import location_matches, strip_html, title_matches

_TIMEOUT = get_timeout("job_boards")
_JSEARCH_FAILURES = 0

logger = logging.getLogger(__name__)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"


def _jsearch_max_consecutive_failures() -> int:
    cfg = load_api_config().get("http", {}).get("job_boards", {})
    try:
        return int(cfg.get("max_consecutive_failures", 3))
    except (TypeError, ValueError):
        return 3


def _jsearch_suppressed() -> bool:
    max_failures = _jsearch_max_consecutive_failures()
    if max_failures <= 0 or _JSEARCH_FAILURES < max_failures:
        return False

    logger.warning(
        "[jsearch] skipped after %s consecutive failure(s)",
        _JSEARCH_FAILURES,
    )
    return True


def _parse_arbeitnow_date(value: int | float | str | None) -> str:
    """Return YYYY-MM-DD from a Unix timestamp int or ISO string, or '' on failure."""
    if not value:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d")
        return str(value)[:10]
    except Exception:
        return ""


def fetch_arbeitnow_jobs(
    title_filters: list[str],
    location_filter: str,
    max_pages: int = 3,
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """
    Fetch jobs from Arbeitnow. Free, no auth required.
    Paginates up to max_pages; stops early when a page returns no data.
    """
    jobs = []

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(ARBEITNOW_URL, params={"page": page}, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"[arbeitnow] page {page}: {e}")
            break

        if not data:
            break

        for job in data:
            title = job.get("title", "")
            location = job.get("location", "")

            if not title_matches(title, title_filters, excluded_title_terms):
                continue
            if not location_matches(location, location_filter):
                continue

            description = strip_html(job.get("description", ""))
            jobs.append(
                {
                    "title": title,
                    "company": job.get("company_name", ""),
                    "url": job.get("url", ""),
                    "posted": _parse_arbeitnow_date(job.get("created_at")),
                    "snippet": f"{location} — {description[:1000]}"
                    if location
                    else description[:1000],
                    "source": "Arbeitnow",
                }
            )

    logger.info(f"[arbeitnow] {len(jobs)} matching jobs")
    return jobs


def fetch_jsearch_jobs(
    title_filters: list[str],
    location_filter: str,
    rapidapi_key: str,
    num_pages: int = 1,
    excluded_title_terms: list[str] | None = None,
    country: str = "",
    language: str = "",
) -> list[dict]:
    """
    Fetch jobs via JSearch on RapidAPI. Aggregates LinkedIn, Indeed, Glassdoor.
    Issues one request per title (to stay within the free tier of 200 req/month).
    Returns [] immediately if no API key is provided.
    """
    global _JSEARCH_FAILURES

    if not rapidapi_key:
        logger.warning("[jsearch] No RAPIDAPI_KEY configured — skipping")
        return []

    headers = {
        "X-RapidAPI-Key": rapidapi_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }

    if not title_filters:
        logger.warning("[jsearch] No configured job titles; skipping")
        return []

    if _jsearch_suppressed():
        return []

    exclusions = " ".join(f'-"{term}"' for term in (excluded_title_terms or []))
    jobs = []

    for title in title_filters:
        query = f"{title} in {location_filter}" if location_filter else title
        if exclusions:
            query = f"{query} {exclusions}"

        for page in range(1, num_pages + 1):
            params = {
                "query": query,
                "page": str(page),
                "num_pages": "1",
            }
            if country:
                params["country"] = country.lower()
            if language:
                params["language"] = language

            if not reserve_api_call("jsearch"):
                return jobs

            try:
                resp = requests.get(
                    JSEARCH_URL,
                    headers=headers,
                    params=params,
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                _JSEARCH_FAILURES = 0
            except Exception as e:
                if is_api_quota_exhausted(e):
                    mark_api_exhausted("jsearch", exc=e)
                    return jobs
                _JSEARCH_FAILURES += 1
                max_failures = _jsearch_max_consecutive_failures()
                logger.warning(
                    "[jsearch] query=%r page=%s: %s (failure %s/%s)",
                    query,
                    page,
                    e,
                    _JSEARCH_FAILURES,
                    max_failures,
                )
                break

            for job in data:
                job_title = job.get("job_title", "")
                if not title_matches(job_title, title_filters, excluded_title_terms):
                    continue

                city = job.get("job_city") or ""
                job_country = job.get("job_country") or ""
                location_str = f"{city}, {job_country}".strip(", ")

                if location_filter and (city or job_country):
                    if not location_matches(city, location_filter) and not location_matches(
                        location_str, location_filter
                    ):
                        continue

                description = (job.get("job_description") or "")[:1000]

                jobs.append(
                    {
                        "title": job_title,
                        "company": job.get("employer_name", ""),
                        "url": job.get("job_apply_link", ""),
                        "posted": (job.get("job_posted_at_datetime_utc") or "")[:10],
                        "snippet": f"{location_str} — {description}"
                        if location_str
                        else description,
                        "source": "JSearch",
                    }
                )

    logger.info(f"[jsearch] {len(jobs)} jobs returned")
    return jobs
