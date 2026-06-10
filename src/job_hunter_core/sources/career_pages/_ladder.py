"""Main extraction ladder coordinator for career pages."""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout
from job_hunter_core.sources.search_providers import USER_AGENT, extract_jobs_from_html
from job_hunter_core.sources.career_pages._ats_patterns import (
    detect_ats,
    _fetch_ats_endpoint_jobs,
)
from job_hunter_core.sources.career_pages._jsonld import extract_jsonld_jobs
from job_hunter_core.sources.career_pages._sitemap import discover_via_sitemap
from job_hunter_core.sources.career_pages._rendering import (
    extract_from_lightpanda,
    extract_from_rendered_html,
    extract_from_firecrawl,
)

logger = logging.getLogger(__name__)


def extract_career_page_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Run the full extraction ladder for a company career URL.

    Returns jobs with ``extraction_method`` set to the rung that produced them:
    ``ats_api``, ``jsonld``, ``sitemap``, ``static_html``, or ``playwright``.

    No search provider or LLM is called at any rung.
    """
    career_url = company.get("career_url", "")
    name = company.get("name", "")
    location = company.get("location", "")

    if not career_url:
        return []

    # Rung 1: ATS public endpoint
    ats_name, slug, api_template = detect_ats(career_url)
    if ats_name and api_template:
        jobs = _fetch_ats_endpoint_jobs(
            slug, ats_name, api_template, title_filters, excluded_title_terms
        )
        if jobs:
            logger.debug(
                "[career_pages] rung=ats_api company=%s ats=%s jobs=%d",
                name,
                ats_name,
                len(jobs),
            )
            return jobs

    # Rung 2: JSON-LD on the career page HTML
    url = career_url if "://" in career_url else f"https://{career_url}"
    timeout = get_timeout("ats_scraper")
    html_content = ""
    html_base_url = url
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        html_content = resp.text
        html_base_url = resp.url or url
    except Exception as exc:
        logger.debug("[career_pages] initial HTML fetch failed for %s: %s", career_url, exc)

    if html_content:
        jsonld_jobs = extract_jsonld_jobs(html_content, html_base_url, name)
        if jsonld_jobs:
            logger.debug("[career_pages] rung=jsonld company=%s jobs=%d", name, len(jsonld_jobs))
            return jsonld_jobs

    # Rung 3: Sitemap / common career-path discovery
    sitemap_jobs = discover_via_sitemap(career_url, name, title_filters, excluded_title_terms)
    if sitemap_jobs:
        logger.debug("[career_pages] rung=sitemap company=%s jobs=%d", name, len(sitemap_jobs))
        return sitemap_jobs

    # Rung 4: Static HTML extraction (reuses already-fetched HTML when available)
    if html_content:
        raw_jobs = extract_jobs_from_html(
            html_content,
            html_base_url,
            name,
            title_filters,
            location,
            "career_page:static_html",
            excluded_title_terms,
        )
        for job in raw_jobs:
            job["extraction_method"] = "static_html"
        if raw_jobs:
            logger.debug("[career_pages] rung=static_html company=%s jobs=%d", name, len(raw_jobs))
            return raw_jobs

    # Rung 5: Lightpanda read-only rendering
    lightpanda_jobs = extract_from_lightpanda(company, title_filters, excluded_title_terms)
    if lightpanda_jobs:
        logger.debug(
            "[career_pages] rung=lightpanda company=%s jobs=%d", name, len(lightpanda_jobs)
        )
        return lightpanda_jobs

    # Rung 6: Playwright rendering (only when all cheaper rungs yield nothing)
    pw_jobs = extract_from_rendered_html(
        career_url, name, title_filters, location, excluded_title_terms
    )
    if pw_jobs:
        logger.debug("[career_pages] rung=playwright company=%s jobs=%d", name, len(pw_jobs))
        return pw_jobs

    # Rung 7: Firecrawl cloud markdown when local extraction remains weak.
    firecrawl_jobs = extract_from_firecrawl(company, title_filters, excluded_title_terms)
    if firecrawl_jobs:
        logger.debug("[career_pages] rung=firecrawl company=%s jobs=%d", name, len(firecrawl_jobs))
    return firecrawl_jobs
