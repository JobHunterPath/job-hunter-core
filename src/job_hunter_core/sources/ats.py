"""
Direct ATS API scrapers for Greenhouse, Lever, SmartRecruiters, Workable, Ashby,
HiBob, Personio, Recruitee, Breezy, Teamtailor, and Workday.
HiBob career pages are JS-rendered with no public API — Playwright is used instead.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import location_matches, strip_html, title_matches
from job_hunter_core.sources.ats_urls import detect_ats

_TIMEOUT = get_timeout("ats_scraper")
_ATS_CFG = load_api_config().get("http", {}).get("ats_scraper", {}) or {}
_SNIPPET_CHARS = int(_ATS_CFG.get("snippet_chars", 2000))

logger = logging.getLogger(__name__)


# ── Greenhouse ───────────────────────────────────────────────────────────────


def fetch_greenhouse_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Greenhouse public API (no auth required)."""
    try:
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        all_jobs = resp.json().get("jobs", [])
    except Exception as e:
        logger.warning(f"[greenhouse] {slug}: {e}")
        return []

    jobs = []
    for job in all_jobs:
        title = job.get("title", "")
        location = job.get("location", {}).get("name", "")
        url = job.get("absolute_url", "")
        content = strip_html(job.get("content", ""))
        posted = (job.get("updated_at") or "")[:10]

        if not location_matches(location, location_filter):
            logger.debug(f"[greenhouse] skip wrong location: {title} ({location})")
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": posted,
                "location": location,
                "snippet": f"{location} - {content[:_SNIPPET_CHARS]}"
                if location
                else content[:_SNIPPET_CHARS],
                "source": "Greenhouse API",
            }
        )

    logger.info(f"[greenhouse] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── Lever ────────────────────────────────────────────────────────────────────


def fetch_lever_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Lever public API (no auth required)."""
    try:
        resp = requests.get(
            f"https://api.lever.co/v0/postings/{slug}",
            params={"mode": "json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json()
    except Exception as e:
        logger.warning(f"[lever] {slug}: {e}")
        return []

    if isinstance(postings, dict):
        postings = postings.get("postings", [])

    jobs = []
    for posting in postings:
        title = posting.get("text", "")
        categories = posting.get("categories", {})
        primary = categories.get("location", "")
        all_locations = list(categories.get("allLocations") or ([primary] if primary else []))
        if primary and primary not in all_locations:
            all_locations.insert(0, primary)

        url = posting.get("hostedUrl", "")
        plain = posting.get("descriptionPlain") or strip_html(posting.get("description", ""))
        created_ms = posting.get("createdAt")
        posted = (
            datetime.fromtimestamp(created_ms / 1000).strftime("%Y-%m-%d") if created_ms else ""
        )

        if location_filter and all_locations:
            if not any(location_matches(loc, location_filter) for loc in all_locations):
                logger.debug(f"[lever] skip wrong location: {title} ({all_locations})")
                continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        display_location = primary or (all_locations[0] if all_locations else "")
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": posted,
                "location": display_location,
                "snippet": (
                    f"{display_location} - {plain[:_SNIPPET_CHARS]}"
                    if display_location
                    else plain[:_SNIPPET_CHARS]
                ),
                "source": "Lever API",
            }
        )

    logger.info(f"[lever] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── SmartRecruiters ──────────────────────────────────────────────────────────


def fetch_smartrecruiters_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """
    Fetch jobs from SmartRecruiters public API (no auth required).
    Makes a second request per matched job to retrieve the full description.
    """
    params: dict = {"limit": 100}
    if location_filter:
        params["city"] = location_filter

    try:
        resp = requests.get(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("content", [])
    except Exception as e:
        logger.warning(f"[smartrecruiters] {slug}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("name", "")
        loc = posting.get("location", {})
        city = loc.get("city", "")
        country = loc.get("country", "")
        location_str = f"{city}, {country}".strip(", ")

        if location_filter and city and not location_matches(city, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        # Fetch full job description (N+1, only for filtered matches)
        posting_id = posting.get("id", "")
        snippet = location_str
        if posting_id:
            try:
                detail = requests.get(
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}",
                    timeout=_TIMEOUT,
                )
                if detail.status_code == 200:
                    sections = detail.json().get("jobAd", {}).get("sections", [])
                    body = " ".join(
                        f"{s.get('title', '')}: {strip_html(s.get('text', ''))}" for s in sections
                    )
                    snippet = f"{location_str} - {body[:_SNIPPET_CHARS]}"
            except Exception as e:
                logger.debug(f"[smartrecruiters] detail fetch failed for {posting_id}: {e}")

        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://jobs.smartrecruiters.com/{slug}/{posting_id}",
                "posted": posting.get("releasedDate", ""),
                "location": location_str,
                "snippet": snippet,
                "source": "SmartRecruiters API",
            }
        )

    logger.info(f"[smartrecruiters] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── Workable ─────────────────────────────────────────────────────────────────


def fetch_workable_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Workable public API (no auth required)."""
    try:
        resp = requests.post(
            f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
            json={"query": "", "location": [location_filter] if location_filter else []},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("results", [])
    except Exception as e:
        logger.warning(f"[workable] {slug}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location_str = posting.get("location", {}).get("location", "")

        if location_filter and location_str and not location_matches(location_str, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        shortcode = posting.get("shortcode", "")
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://apply.workable.com/{slug}/j/{shortcode}",
                "posted": posting.get("published_on", ""),
                "location": location_str,
                "snippet": f"{location_str} - {posting.get('department', '')}",
                "source": "Workable API",
            }
        )

    logger.info(f"[workable] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── Ashby ─────────────────────────────────────────────────────────────────────


def fetch_ashby_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Ashby public job-board API (no auth required)."""
    try:
        resp = requests.post(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            json={},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("jobPostings", [])
    except Exception as e:
        logger.warning(f"[ashby] {slug}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location = posting.get("locationName", "")

        if not location_matches(location, location_filter):
            logger.debug(f"[ashby] skip wrong location: {title} ({location})")
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        description = strip_html(posting.get("descriptionHtml", ""))
        url = posting.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{posting.get('id', '')}"
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": (posting.get("publishedAt") or "")[:10],
                "location": location,
                "snippet": (
                    f"{location} - {description[:_SNIPPET_CHARS]}"
                    if location
                    else description[:_SNIPPET_CHARS]
                ),
                "source": "Ashby API",
            }
        )

    logger.info(f"[ashby] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── HiBob ─────────────────────────────────────────────────────────────────────


def fetch_hibob_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """
    Scrape a HiBob career page with Playwright (JS-rendered — no public API).

    Loads the listing page, extracts all job links (UUID-style hrefs), and
    returns jobs with empty snippets. The orchestrator enriches these via
    fetch_jd before validation and scoring.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(f"[hibob] playwright not installed; cannot scrape {slug}.careers.hibob.com")
        return []

    career_url = f"https://{slug}.careers.hibob.com"
    # HiBob job URLs contain a UUID: /jobs/<8-4-4-4-12 hex>
    uuid_re = re.compile(
        r"/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    )

    raw_links: dict[str, str] = {}  # url -> title text
    ats_cfg = load_api_config().get("http", {}).get("ats_scraper", {}) or {}
    playwright_timeout = int(ats_cfg.get("hibob_playwright_timeout_seconds", 25) * 1000)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(career_url, wait_until="networkidle", timeout=playwright_timeout)
                for anchor in page.query_selector_all("a"):
                    href = anchor.get_attribute("href") or ""
                    if not uuid_re.search(href):
                        continue
                    if not href.startswith("http"):
                        href = f"https://{slug}.careers.hibob.com{href}"
                    title_text = (anchor.text_content() or "").strip()
                    if href not in raw_links and title_text:
                        raw_links[href] = title_text
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"[hibob] Playwright failed for {career_url}: {e}")
        return []

    jobs = []
    for url, title in raw_links.items():
        if not title_matches(title, title_filters, excluded_title_terms):
            continue
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": "",
                "location": "",
                # snippet intentionally empty - enriched by orchestrator._enrich_snippets
                "snippet": "",
                "source": "HiBob",
            }
        )

    logger.info(f"[hibob] {slug}: {len(jobs)} matching jobs (from {len(raw_links)} total listings)")
    return jobs


# ---- Personio ----


def fetch_personio_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Personio's public XML feed."""
    try:
        resp = requests.get(f"https://{slug}.jobs.personio.de/xml", timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.text)
    except Exception as e:
        logger.warning(f"[personio] {slug}: {e}")
        return []

    jobs = []
    for position in root.findall(".//position"):
        title = (position.findtext("name") or "").strip()
        location = (position.findtext("office") or "").strip()
        if location_filter and location and not location_matches(location, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        job_id = (position.findtext("id") or "").strip()
        descriptions = []
        for node in position.findall(".//jobDescription"):
            label = (node.findtext("name") or "").strip()
            value = strip_html(node.findtext("value") or "")
            if value:
                descriptions.append(f"{label}: {value}" if label else value)
        body = " ".join(descriptions)
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://{slug}.jobs.personio.de/job/{job_id}"
                if job_id
                else f"https://{slug}.jobs.personio.de",
                "posted": "",
                "location": location,
                "snippet": f"{location} - {body[:_SNIPPET_CHARS]}"
                if location
                else body[:_SNIPPET_CHARS],
                "source": "Personio XML",
            }
        )

    logger.info(f"[personio] {slug}: {len(jobs)} matching jobs")
    return jobs


# ---- Recruitee ----


def fetch_recruitee_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Recruitee's public careers API."""
    try:
        resp = requests.get(f"https://{slug}.recruitee.com/api/offers/", timeout=_TIMEOUT)
        resp.raise_for_status()
        offers = resp.json().get("offers", [])
    except Exception as e:
        logger.warning(f"[recruitee] {slug}: {e}")
        return []

    jobs = []
    for offer in offers:
        title = offer.get("title", "")
        location = offer.get("location", "") or offer.get("city", "")
        if isinstance(location, dict):
            location = ", ".join(str(v) for v in location.values() if v)
        if location_filter and location and not location_matches(str(location), location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        body = strip_html(offer.get("description") or offer.get("description_html") or "")
        url = (
            offer.get("careers_url")
            or offer.get("url")
            or f"https://{slug}.recruitee.com/o/{offer.get('slug', '')}"
        )
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": (offer.get("published_at") or "")[:10],
                "location": str(location),
                "snippet": f"{location} - {body[:_SNIPPET_CHARS]}"
                if location
                else body[:_SNIPPET_CHARS],
                "source": "Recruitee API",
            }
        )

    logger.info(f"[recruitee] {slug}: {len(jobs)} matching jobs")
    return jobs


# ---- Breezy ----


def fetch_breezy_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Breezy's public JSON feed."""
    try:
        resp = requests.get(
            f"https://{slug}.breezy.hr/json", params={"verbose": "true"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        postings = resp.json()
    except Exception as e:
        logger.warning(f"[breezy] {slug}: {e}")
        return []

    if isinstance(postings, dict):
        postings = postings.get("positions") or postings.get("jobs") or []

    jobs = []
    for posting in postings:
        title = posting.get("name") or posting.get("title") or ""
        location = posting.get("location") or ""
        if isinstance(location, dict):
            location = ", ".join(str(v) for v in location.values() if v)
        if location_filter and location and not location_matches(str(location), location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        body = strip_html(posting.get("description") or "")
        slug_or_id = posting.get("friendly_id") or posting.get("id") or ""
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": posting.get("url") or f"https://{slug}.breezy.hr/p/{slug_or_id}",
                "posted": (posting.get("creation_date") or posting.get("published_at") or "")[:10],
                "location": str(location),
                "snippet": f"{location} - {body[:_SNIPPET_CHARS]}"
                if location
                else body[:_SNIPPET_CHARS],
                "source": "Breezy JSON",
            }
        )

    logger.info(f"[breezy] {slug}: {len(jobs)} matching jobs")
    return jobs


# ---- Teamtailor ----


def fetch_teamtailor_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Extract public job links from a Teamtailor careers page."""
    base_url = f"https://{slug}.teamtailor.com/jobs"
    try:
        resp = requests.get(base_url, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[teamtailor] {slug}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    jobs = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/jobs/" not in href:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        title = " ".join((anchor.get_text(" ") or "").split())
        if not title or not title_matches(title, title_filters, excluded_title_terms):
            continue
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": "",
                "location": "",
                "snippet": "",
                "source": "Teamtailor",
            }
        )

    logger.info(f"[teamtailor] {slug}: {len(jobs)} matching jobs")
    return jobs


# ---- Workday ----


def fetch_workday_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch Workday jobs from the public CXS listing endpoint where available."""
    host_site = slug.strip("/")
    if "/" not in host_site:
        return []
    host, site = host_site.split("/", 1)
    tenant = host.split(".")[0]
    base = f"https://{host}"
    try:
        resp = requests.post(
            f"{base}/wday/cxs/{tenant}/{site}/jobs",
            json={"appliedFacets": {}, "limit": 50, "offset": 0, "searchText": ""},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        postings = resp.json().get("jobPostings", [])
    except Exception as e:
        logger.warning(f"[workday] {host_site}: {e}")
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location = posting.get("locationsText") or posting.get("location") or ""
        if location_filter and location and not location_matches(location, location_filter):
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        external_path = posting.get("externalPath") or ""
        url = (
            urljoin(f"{base}/{site}/", external_path.lstrip("/"))
            if external_path
            else f"{base}/{site}"
        )
        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": url,
                "posted": posting.get("postedOn", ""),
                "location": location,
                "snippet": location,
                "source": "Workday CXS",
            }
        )

    logger.info(f"[workday] {host_site}: {len(jobs)} matching jobs")
    return jobs


# ---- Dispatcher ----

_FETCHERS = {
    "greenhouse": fetch_greenhouse_jobs,
    "lever": fetch_lever_jobs,
    "smartrecruiters": fetch_smartrecruiters_jobs,
    "workable": fetch_workable_jobs,
    "ashby": fetch_ashby_jobs,
    "hibob": fetch_hibob_jobs,
    "personio": fetch_personio_jobs,
    "recruitee": fetch_recruitee_jobs,
    "breezy": fetch_breezy_jobs,
    "teamtailor": fetch_teamtailor_jobs,
    "workday": fetch_workday_jobs,
}


def fetch_ats_jobs(
    company: dict,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict] | None:
    """
    Fetch jobs via direct ATS API for a given company.
    Returns None if the career_url is not a recognised ATS (caller should fall back to Brave).
    Returns [] if the ATS was reached but no matching jobs were found.
    """
    detected = detect_ats(company["career_url"])
    if detected is None:
        return None

    ats_name, slug = detected
    fetcher = _FETCHERS.get(ats_name)
    if fetcher is None:
        logger.debug(f"[ats] No fetcher for {ats_name}, falling back to Brave")
        return None

    logger.info(f"[ats] {company['name']} -> {ats_name.capitalize()} (slug={slug})")
    if excluded_title_terms is None:
        return fetcher(slug, company["name"], location_filter, title_filters)
    return fetcher(slug, company["name"], location_filter, title_filters, excluded_title_terms)
