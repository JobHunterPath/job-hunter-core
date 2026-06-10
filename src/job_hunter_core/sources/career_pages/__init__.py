"""Deterministic career-page extraction ladder.

Extraction order (cheapest and most structured first):

1. Known ATS/public endpoint detection: if the URL matches a supported ATS
   platform, fetch jobs from the public JSON API directly.
2. Embedded JobPosting JSON-LD extraction: parse structured data from the
   page HTML without rendering JavaScript.
3. Sitemap / common career-path discovery: probe /sitemap.xml and
   well-known career paths for job-detail URLs.
4. Static HTML extraction: parse anchor links from the raw HTML response.
5. Playwright rendering: only when static extraction yields nothing.

Each rung records ``extraction_method`` in the returned job dict so callers
can tell how a candidate was found without inspecting the URL.

No search provider, LLM, or Kestrel code is used or imported here.
"""

from __future__ import annotations

import logging

import requests  # noqa: F401 — exposed so tests can patch career_pages.requests.get/head

from job_hunter_core.sources.career_pages._ats_patterns import (
    _ATS_URL_PATTERNS,
    _CAREER_PATHS,
    detect_ats,
    _normalise_ats_job,
    _fetch_ats_endpoint_jobs,
)
from job_hunter_core.sources.career_pages._jsonld import extract_jsonld_jobs
from job_hunter_core.sources.career_pages._sitemap import (
    _probe_sitemap,
    _probe_career_paths,
    discover_via_sitemap,
)
from job_hunter_core.sources.career_pages._rendering import (
    extract_from_static_html,
    extract_from_rendered_html,
    extract_from_lightpanda,
    extract_from_firecrawl,
)
from job_hunter_core.sources.career_pages._ladder import extract_career_page_jobs

logger = logging.getLogger(__name__)

__all__ = [
    "detect_ats",
    "extract_jsonld_jobs",
    "discover_via_sitemap",
    "extract_from_static_html",
    "extract_from_rendered_html",
    "extract_from_lightpanda",
    "extract_from_firecrawl",
    "extract_career_page_jobs",
    "_ATS_URL_PATTERNS",
    "_CAREER_PATHS",
    "_normalise_ats_job",
    "_fetch_ats_endpoint_jobs",
    "_probe_sitemap",
    "_probe_career_paths",
]
