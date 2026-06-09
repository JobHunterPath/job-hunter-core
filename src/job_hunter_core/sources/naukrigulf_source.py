"""Naukrigulf — Gulf region job board by Naukri (India/Gulf).

Tier 3: requests with headers first; falls back to Playwright if the response is blocked.
Only fires for regions with country code in the Gulf set.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.naukrigulf.com"

_GULF_CODES: frozenset[str] = frozenset({"AE", "SA", "QA", "KW", "BH", "OM"})

_COUNTRY_SLUGS: dict[str, str] = {
    "AE": "uae",
    "SA": "saudi-arabia",
    "QA": "qatar",
    "KW": "kuwait",
    "BH": "bahrain",
    "OM": "oman",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.naukrigulf.com/",
}


def _build_url(title: str, country_slug: str) -> str:
    slug = title.lower().replace(" ", "-").replace("/", "-")
    return f"{_BASE_URL}/{slug}-jobs-in-{country_slug}"


def _parse_cards(
    html: str,
    title_filters: list[str],
    excluded_title_terms: list[str],
    region_name: str,
    title_query: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = (
        soup.find_all(
            "div", {"class": re.compile(r"job.?tuple|jobTuple|job.?card|srp-tuple", re.I)}
        )
        or soup.find_all("article", {"class": re.compile(r"job", re.I)})
        or soup.select("li.job, div[data-job-id], div.job-wrap")
    )
    jobs = []
    for card in cards:
        title_tag = (
            card.find("a", {"class": re.compile(r"job.?title|designation|title", re.I)})
            or card.find("h2")
            or card.find("h3")
        )
        job_title = title_tag.get_text(strip=True) if title_tag else ""
        if not job_title:
            continue
        if not title_matches(job_title, title_filters, excluded_title_terms):
            continue

        company_tag = card.find(class_=re.compile(r"company|org|employer|comp-name", re.I))
        company = company_tag.get_text(strip=True) if company_tag else ""

        link = title_tag if (title_tag and title_tag.name == "a") else card.find("a", href=True)
        href = link.get("href", "") if link else ""
        if href and not href.startswith("http"):
            href = _BASE_URL + href

        location_tag = card.find(class_=re.compile(r"location|loc|city", re.I))
        job_location = location_tag.get_text(strip=True) if location_tag else ""

        date_tag = card.find(class_=re.compile(r"date|posted|freshness", re.I))
        posted = date_tag.get_text(strip=True) if date_tag else ""

        desc_tag = card.find(class_=re.compile(r"description|snippet|job-desc", re.I))
        snippet = strip_html(desc_tag.get_text(strip=True) if desc_tag else "")

        jobs.append(
            {
                "title": job_title,
                "company": company,
                "url": href,
                "posted": posted,
                "location": job_location,
                "snippet": snippet[:3000],
                "source": "Naukrigulf",
                "query": f"{title_query} @ {region_name}",
                "region": region_name,
            }
        )
    return jobs


def _fetch_with_playwright(url: str, timeout_ms: int, user_agent: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[naukrigulf] playwright not installed; skipping rendered fallback")
        return ""
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=user_agent)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
            finally:
                browser.close()
        return html
    except Exception as exc:
        logger.debug("[naukrigulf] Playwright render failed for %s: %s", url, exc)
        return ""


def fetch_naukrigulf_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch jobs from Naukrigulf using requests→Playwright fallback.

    Only runs for Gulf regions (AE, SA, QA, KW, BH, OM).
    """
    source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("naukrigulf", {}) or {}
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    timeout_ms = timeout * 1000
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        iso = region_config.get("country", "").upper()
        if iso not in _GULF_CODES:
            continue
        country_slug = _COUNTRY_SLUGS.get(iso, iso.lower())

        for title in title_filters:
            url = _build_url(title, country_slug)
            html = ""
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=timeout)
                if resp.status_code == 200 and len(resp.text) > 200:
                    html = resp.text
            except Exception as exc:
                logger.debug(
                    "[naukrigulf] requests failed for %r in %s: %s", title, region_name, exc
                )

            if not html:
                logger.debug(
                    "[naukrigulf] falling back to Playwright for %r in %s", title, region_name
                )
                html = _fetch_with_playwright(url, timeout_ms, _HEADERS["User-Agent"])

            if not html:
                logger.warning("[naukrigulf] no HTML for %r in %s", title, region_name)
                continue

            before = len(jobs)
            new_jobs = _parse_cards(html, title_filters, excluded_title_terms, region_name, title)
            jobs.extend(new_jobs)
            logger.info(
                "[naukrigulf] +%d jobs for %r in %s", len(jobs) - before, title, region_name
            )

    logger.info("[naukrigulf] Complete: %d total jobs", len(jobs))
    return jobs
