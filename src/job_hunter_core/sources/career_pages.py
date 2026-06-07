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

import json
import logging
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from job_hunter_core.core.config import get_timeout
from job_hunter_core.sources.search_providers import (
    USER_AGENT,
    canonicalize_url,
    extract_jobs_from_html,
    fetch_firecrawl_career_jobs,
    fetch_lightpanda_career_jobs,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Rung 1: ATS public endpoint
# ---------------------------------------------------------------------------


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
        "snippet": str(raw.get("content") or raw.get("description") or "")[:400].strip(),
        "source": f"career_page:ats_api:{ats_name}",
        "extraction_method": "ats_api",
        "detected_ats": ats_name,
    }


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


# ---------------------------------------------------------------------------
# Rung 2: JSON-LD JobPosting extraction
# ---------------------------------------------------------------------------


def extract_jsonld_jobs(
    html: str,
    base_url: str,
    company_name: str,
) -> list[dict]:
    """Parse embedded JobPosting JSON-LD blocks from page HTML.

    Follows the schema.org JobPosting type as documented at
    https://schema.org/JobPosting and Google's job posting structured data
    guidance at https://developers.google.com/search/docs/appearance/structured-data/job-posting.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    for script_tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            payload = json.loads(script_tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # May be a single object or a list; flatten @graph wrappers before iterating
        # so that inner items are not missed when the for-loop iterator is already bound.
        raw_items = payload if isinstance(payload, list) else [payload]
        items: list = []
        for raw in raw_items:
            if isinstance(raw, dict) and "@graph" in raw:
                inner = raw["@graph"]
                if isinstance(inner, list):
                    items.extend(d for d in inner if isinstance(d, dict))
            elif isinstance(raw, dict):
                items.append(raw)

        for item in items:
            type_val = item.get("@type", "")
            if type_val != "JobPosting" and "JobPosting" not in (
                type_val if isinstance(type_val, list) else [type_val]
            ):
                continue

            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                continue

            apply_url = ""
            apply_info = item.get("apply") or item.get("applyUrl") or {}
            if isinstance(apply_info, dict):
                apply_url = str(apply_info.get("url") or "").strip()
            elif isinstance(apply_info, str):
                apply_url = apply_info.strip()

            job_url = apply_url or base_url
            canonical = canonicalize_url(job_url)
            if canonical in seen:
                continue
            seen.add(canonical)

            location_raw = item.get("jobLocation") or {}
            if isinstance(location_raw, dict):
                address = location_raw.get("address") or {}
                if isinstance(address, dict):
                    location = (
                        address.get("addressLocality")
                        or address.get("addressRegion")
                        or address.get("addressCountry")
                        or ""
                    )
                else:
                    location = str(address)
            elif isinstance(location_raw, str):
                location = location_raw
            else:
                location = ""

            employer_raw = item.get("hiringOrganization") or {}
            if isinstance(employer_raw, dict):
                employer = str(employer_raw.get("name") or company_name).strip()
            else:
                employer = company_name

            description_raw = item.get("description") or ""
            snippet = str(description_raw)[:400].strip()

            jobs.append(
                {
                    "title": title,
                    "company": employer,
                    "url": job_url,
                    "location": str(location).strip(),
                    "posted": str(item.get("datePosted") or "").strip(),
                    "snippet": snippet,
                    "source": "career_page:jsonld",
                    "extraction_method": "jsonld",
                    "raw_schema_org": item,
                }
            )

    return jobs


# ---------------------------------------------------------------------------
# Rung 3: Sitemap / common career-path discovery
# ---------------------------------------------------------------------------


def _probe_sitemap(base_url: str, timeout: int) -> list[str]:
    """Return job-detail URLs found in /sitemap.xml."""
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    try:
        resp = requests.get(
            sitemap_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")
        return [loc.get_text(strip=True) for loc in soup.find_all("loc")]
    except Exception:
        return []


def _probe_career_paths(base_url: str, timeout: int) -> list[str]:
    """Return URLs that responded successfully from common career-page paths."""
    found = []
    for path in _CAREER_PATHS:
        url = base_url.rstrip("/") + path
        try:
            resp = requests.head(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.ok:
                found.append(resp.url or url)
        except Exception:
            pass
    return found


def discover_via_sitemap(
    career_url: str,
    company_name: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Return job-detail URLs discovered through sitemap or common career paths."""
    parsed = urlparse(career_url if "://" in career_url else f"https://{career_url}")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    timeout = get_timeout("ats_scraper")

    candidate_urls: list[str] = []

    sitemap_locs = _probe_sitemap(base_url, timeout)
    job_hint_locs = [
        loc
        for loc in sitemap_locs
        if any(hint in loc.lower() for hint in ("/job", "/career", "/position", "/opening"))
    ]
    candidate_urls.extend(job_hint_locs)

    if not candidate_urls:
        candidate_urls.extend(_probe_career_paths(base_url, timeout))

    jobs: list[dict] = []
    seen: set[str] = set()
    from job_hunter_core.core.utils import title_matches

    for url in candidate_urls:
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        if not title_matches(url, title_filters, excluded_title_terms):
            continue
        jobs.append(
            {
                "title": "",
                "company": company_name,
                "url": url,
                "location": "",
                "posted": "",
                "snippet": "",
                "source": "career_page:sitemap",
                "extraction_method": "sitemap",
            }
        )

    return jobs


# ---------------------------------------------------------------------------
# Rung 4: Static HTML extraction
# ---------------------------------------------------------------------------


def extract_from_static_html(
    career_url: str,
    company_name: str,
    title_filters: list[str],
    location: str = "",
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch and parse static HTML to find job-detail links."""
    url = career_url if "://" in career_url else f"https://{career_url}"
    timeout = get_timeout("ats_scraper")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.debug("[career_pages] static HTML fetch failed for %s: %s", career_url, exc)
        return []

    raw_jobs = extract_jobs_from_html(
        resp.text,
        resp.url or url,
        company_name,
        title_filters,
        location,
        "career_page:static_html",
        excluded_title_terms,
    )
    for job in raw_jobs:
        job["extraction_method"] = "static_html"
    return raw_jobs


# ---------------------------------------------------------------------------
# Rung 5: Playwright rendering
# ---------------------------------------------------------------------------


def extract_from_rendered_html(
    career_url: str,
    company_name: str,
    title_filters: list[str],
    location: str = "",
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Render a JavaScript-heavy career page with Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[career_pages] playwright not installed; skipping rendered extraction")
        return []

    url = career_url if "://" in career_url else f"https://{career_url}"
    pw_timeout_ms = int(get_timeout("playwright") * 1000)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=pw_timeout_ms)
                html = page.content()
                final_url = page.url or url
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("[career_pages] Playwright render failed for %s: %s", career_url, exc)
        return []

    raw_jobs = extract_jobs_from_html(
        html,
        final_url,
        company_name,
        title_filters,
        location,
        "career_page:playwright",
        excluded_title_terms,
    )
    for job in raw_jobs:
        job["extraction_method"] = "playwright"
    return raw_jobs


def extract_from_lightpanda(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Render a public page with Lightpanda when the binary is available."""
    jobs = fetch_lightpanda_career_jobs(company, title_filters, excluded_title_terms)
    for job in jobs:
        job["extraction_method"] = "lightpanda"
    return jobs


def extract_from_firecrawl(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Scrape public pages through Firecrawl when key and budget are available."""
    jobs = fetch_firecrawl_career_jobs(company, title_filters, excluded_title_terms)
    for job in jobs:
        job["extraction_method"] = "firecrawl"
    return jobs


# ---------------------------------------------------------------------------
# Main ladder entry point
# ---------------------------------------------------------------------------


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
