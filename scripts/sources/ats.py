"""
Direct ATS API scrapers for Greenhouse, Lever, SmartRecruiters, Workable, and Ashby.
HiBob career pages are JS-rendered with no public API — Playwright is used instead.
"""

import re
import logging
from datetime import datetime
import requests

from core.config import get_timeout
from core.utils import strip_html, location_matches, title_matches

_TIMEOUT = get_timeout("ats_scraper")

logger = logging.getLogger(__name__)

# Maps ATS name → regex matching the normalised career_url (scheme stripped, trailing slash removed).
_ATS_PATTERNS = {
    # Greenhouse uses both boards. and job-boards. subdomains
    "greenhouse":      r"^(?:boards|job-boards)\.greenhouse\.io/([^/]+)$",
    "lever":           r"^jobs\.lever\.co/([^/]+)$",
    "smartrecruiters": r"^jobs\.smartrecruiters\.com/([^/]+)$",
    "workable":        r"^apply\.workable\.com/([^/]+)$",
    "ashby":           r"^jobs\.ashbyhq\.com/([^/]+)$",
    # HiBob: {slug}.careers.hibob.com (subdomain carries the company slug)
    "hibob":           r"^([^./]+)\.careers\.hibob\.com$",
}


def detect_ats(career_url: str) -> tuple[str, str] | None:
    """
    Identify which ATS platform a career_url belongs to.
    Returns (ats_name, slug) or None for unknown/direct career pages.
    """
    url = re.sub(r"^https?://", "", career_url).rstrip("/")
    for ats, pattern in _ATS_PATTERNS.items():
        m = re.match(pattern, url)
        if m:
            return ats, m.group(1)
    return None


# ── Greenhouse ───────────────────────────────────────────────────────────────

def fetch_greenhouse_jobs(
    slug: str, company_name: str, location_filter: str, title_filters: list[str],
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

        jobs.append({
            "title": title,
            "company": company_name,
            "url": url,
            "posted": posted,
            "snippet": f"{location} — {content[:2000]}" if location else content[:2000],
            "source": "Greenhouse API",
        })

    logger.info(f"[greenhouse] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── Lever ────────────────────────────────────────────────────────────────────

def fetch_lever_jobs(
    slug: str, company_name: str, location_filter: str, title_filters: list[str],
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
        posted = datetime.fromtimestamp(created_ms / 1000).strftime("%Y-%m-%d") if created_ms else ""

        if location_filter and all_locations:
            if not any(location_matches(loc, location_filter) for loc in all_locations):
                logger.debug(f"[lever] skip wrong location: {title} ({all_locations})")
                continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        display_location = primary or (all_locations[0] if all_locations else "")
        jobs.append({
            "title": title,
            "company": company_name,
            "url": url,
            "posted": posted,
            "snippet": f"{display_location} — {plain[:2000]}" if display_location else plain[:2000],
            "source": "Lever API",
        })

    logger.info(f"[lever] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── SmartRecruiters ──────────────────────────────────────────────────────────

def fetch_smartrecruiters_jobs(
    slug: str, company_name: str, location_filter: str, title_filters: list[str],
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
                        f"{s.get('title', '')}: {strip_html(s.get('text', ''))}"
                        for s in sections
                    )
                    snippet = f"{location_str} — {body[:2000]}"
            except Exception as e:
                logger.debug(f"[smartrecruiters] detail fetch failed for {posting_id}: {e}")

        jobs.append({
            "title": title,
            "company": company_name,
            "url": f"https://jobs.smartrecruiters.com/{slug}/{posting_id}",
            "posted": posting.get("releasedDate", ""),
            "snippet": snippet,
            "source": "SmartRecruiters API",
        })

    logger.info(f"[smartrecruiters] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── Workable ─────────────────────────────────────────────────────────────────

def fetch_workable_jobs(
    slug: str, company_name: str, location_filter: str, title_filters: list[str],
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
        jobs.append({
            "title": title,
            "company": company_name,
            "url": f"https://apply.workable.com/{slug}/j/{shortcode}",
            "posted": posting.get("published_on", ""),
            "snippet": f"{location_str} — {posting.get('department', '')}",
            "source": "Workable API",
        })

    logger.info(f"[workable] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── Ashby ─────────────────────────────────────────────────────────────────────

def fetch_ashby_jobs(
    slug: str, company_name: str, location_filter: str, title_filters: list[str],
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
        jobs.append({
            "title": title,
            "company": company_name,
            "url": url,
            "posted": (posting.get("publishedAt") or "")[:10],
            "snippet": f"{location} — {description[:2000]}" if location else description[:2000],
            "source": "Ashby API",
        })

    logger.info(f"[ashby] {slug}: {len(jobs)} matching jobs")
    return jobs


# ── HiBob ─────────────────────────────────────────────────────────────────────

def fetch_hibob_jobs(
    slug: str, company_name: str, location_filter: str, title_filters: list[str],
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

    raw_links: dict[str, str] = {}  # url → title text
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(career_url, wait_until="networkidle", timeout=25_000)
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
        jobs.append({
            "title": title,
            "company": company_name,
            "url": url,
            "posted": "",
            # snippet intentionally empty — enriched by orchestrator._enrich_snippets
            "snippet": "",
            "source": "HiBob",
        })

    logger.info(f"[hibob] {slug}: {len(jobs)} matching jobs (from {len(raw_links)} total listings)")
    return jobs


# ── Dispatcher ───────────────────────────────────────────────────────────────

_FETCHERS = {
    "greenhouse":      fetch_greenhouse_jobs,
    "lever":           fetch_lever_jobs,
    "smartrecruiters": fetch_smartrecruiters_jobs,
    "workable":        fetch_workable_jobs,
    "ashby":           fetch_ashby_jobs,
    "hibob":           fetch_hibob_jobs,
}


def fetch_ats_jobs(
    company: dict, location_filter: str, title_filters: list[str],
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

    logger.info(f"[ats] {company['name']} → {ats_name.capitalize()} (slug={slug})")
    if excluded_title_terms is None:
        return fetcher(slug, company["name"], location_filter, title_filters)
    return fetcher(slug, company["name"], location_filter, title_filters, excluded_title_terms)
