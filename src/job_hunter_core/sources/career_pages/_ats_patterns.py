"""ATS URL pattern detection and public endpoint fetching."""

from __future__ import annotations

import re

import requests

from job_hunter_core.core.config import get_timeout
from job_hunter_core.sources.search_providers import USER_AGENT

_SNIPPET_CHARS = 400  # initial snippet length for ATS pattern-matched jobs before enrichment

# Maps a compiled URL pattern to (ats_name, public_api_url_template).
# The template receives {slug} and optionally {job_id} via .format().
_ATS_URL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", re.IGNORECASE),
        "greenhouse",
        "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    ),
    (
        re.compile(r"jobs\.lever\.co/([^/?#]+)", re.IGNORECASE),
        "lever",
        "https://api.lever.co/v0/postings/{slug}?mode=json",
    ),
    (
        re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.IGNORECASE),
        "ashby",
        "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    ),
    (
        re.compile(r"jobs\.smartrecruiters\.com/([^/?#]+)", re.IGNORECASE),
        "smartrecruiters",
        "https://api.smartrecruiters.com/v1/companies/{slug}/postings?status=PUBLISHED",
    ),
    (
        re.compile(r"apply\.workable\.com/([^/?#]+)", re.IGNORECASE),
        "workable",
        "https://apply.workable.com/api/v3/accounts/{slug}/jobs?details=true&status=published",
    ),
    (
        re.compile(r"([^./]+)\.jobs\.personio\.de", re.IGNORECASE),
        "personio",
        "https://{slug}.jobs.personio.de/api/v1/jobs",
    ),
    (
        re.compile(r"([^./]+)\.recruitee\.com", re.IGNORECASE),
        "recruitee",
        "https://{slug}.recruitee.com/api/offers",
    ),
    (
        re.compile(r"([^./]+)\.teamtailor\.com", re.IGNORECASE),
        "teamtailor",
        "",  # Teamtailor does not expose a public unauthenticated jobs JSON API
    ),
    (
        re.compile(r"([^./]+)\.breezy\.hr", re.IGNORECASE),
        "breezy",
        "https://{slug}.breezy.hr/json",
    ),
    (
        re.compile(r"([^./]+)\.myworkdayjobs\.com", re.IGNORECASE),
        "workday",
        "",  # Workday jobs API requires site-specific discovery
    ),
]

# Common career-page paths to probe when the base URL is not an ATS subdomain.
_CAREER_PATHS = [
    "/careers",
    "/jobs",
    "/job-openings",
    "/open-positions",
    "/work-with-us",
    "/join-us",
]


def detect_ats(url: str) -> tuple[str, str, str]:
    """Return (ats_name, slug, api_url_template) for the given URL, or ('', '', '') if unknown."""
    for pattern, ats_name, api_template in _ATS_URL_PATTERNS:
        m = pattern.search(url)
        if m:
            slug = m.group(1).rstrip("/")
            return ats_name, slug, api_template
    return "", "", ""


def _normalise_ats_job(raw: dict, ats_name: str, slug: str, base_url: str) -> dict | None:
    """Convert a raw ATS API job object into a minimal job dict."""
    title = raw.get("title") or raw.get("text") or raw.get("name") or ""
    if not title:
        return None

    url = (
        raw.get("absolute_url")
        or raw.get("hostedUrl")
        or raw.get("applyUrl")
        or raw.get("url")
        or ""
    )

    # Greenhouse wraps location as an object
    location_raw = raw.get("location") or raw.get("locationName") or ""
    if isinstance(location_raw, dict):
        location = location_raw.get("name", "")
    else:
        location = str(location_raw)

    company = slug.replace("-", " ").replace("_", " ").title()

    return {
        "title": str(title).strip(),
        "company": company,
        "url": str(url).strip(),
        "location": location.strip(),
        "posted": str(raw.get("updated_at") or raw.get("createdAt") or "").strip(),
        "snippet": str(raw.get("content") or raw.get("description") or "")[:_SNIPPET_CHARS].strip(),
        "source": f"career_page:ats_api:{ats_name}",
        "extraction_method": "ats_api",
        "detected_ats": ats_name,
    }


import logging  # noqa: E402

logger = logging.getLogger(__name__)


def _fetch_ats_endpoint_jobs(
    slug: str,
    ats_name: str,
    api_url_template: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None,
) -> list[dict]:
    if not api_url_template:
        return []

    api_url = api_url_template.format(slug=slug)
    timeout = get_timeout("ats_scraper")
    try:
        resp = requests.get(
            api_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("[career_pages] ATS API fetch failed (%s, %s): %s", ats_name, slug, exc)
        return []

    # Normalise different ATS response shapes to a flat list of job dicts
    raw_jobs: list[dict] = []
    if isinstance(data, list):
        raw_jobs = data
    elif isinstance(data, dict):
        for key in ("jobs", "postings", "offers", "results", "content"):
            if isinstance(data.get(key), list):
                raw_jobs = data[key]
                break

    jobs = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        job = _normalise_ats_job(raw, ats_name, slug, api_url)
        if job and job.get("url"):
            jobs.append(job)

    logger.debug(
        "[career_pages] ATS API (%s, %s): %d raw -> %d normalised",
        ats_name,
        slug,
        len(raw_jobs),
        len(jobs),
    )
    return jobs
