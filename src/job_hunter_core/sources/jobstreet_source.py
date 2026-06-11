"""JobStreet — Southeast Asia job board (SG, MY, ID, PH, VN).

Tier 3: REST API with session headers first; falls back to Playwright.
Only fires for SEA regions (SG, MY, ID, PH, VN).
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_PAGE_SIZE = 30

# country ISO → (siteKey, domain)
_SEA_CONFIG: dict[str, tuple[str, str]] = {
    "SG": ("SG-Main", "jobstreet.com.sg"),
    "MY": ("MY-Main", "jobstreet.com.my"),
    "ID": ("ID-Main", "jobstreet.co.id"),
    "PH": ("PH-Main", "jobstreet.com.ph"),
    "VN": ("VN-Main", "jobstreet.com.vn"),
}


def _api_url(domain: str) -> str:
    return f"https://www.{domain}/api/chalice-search/v4/search"


def _job_url(domain: str, job_id: str) -> str:
    return f"https://www.{domain}/job/{job_id}"


def _headers(domain: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.{domain}/jobs/",
    }


def _fetch_page_playwright(
    domain: str, site_key: str, title: str, page: int, timeout_ms: int
) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[jobstreet] playwright not installed; skipping rendered fallback")
        return []

    search_url = f"https://www.{domain}/jobs/{title.lower().replace(' ', '-')}?pg={page}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page_obj = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page_obj.goto(search_url, wait_until="networkidle", timeout=timeout_ms)
                # Try to intercept the chalice API response from the rendered page
                html = page_obj.content()
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("[jobstreet] Playwright render failed for %s: %s", search_url, exc)
        return []

    # Extract job data from embedded JSON in HTML
    import re

    matches = re.findall(r'"jobId"\s*:\s*"([^"]+)"', html)
    if not matches:
        return []

    # Return minimal stubs; full data not parseable without deeper extraction
    jobs = []
    for job_id in matches:
        jobs.append(
            {
                "_id": job_id,
                "_domain": domain,
                "_stub": True,
            }
        )
    return jobs


class JobStreetSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "jobstreet"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = (
            load_api_config().get("http", {}).get("job_boards", {}).get("jobstreet", {}) or {}
        )
        return bool(source_cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from JobStreet using REST API with Playwright fallback.

        Only runs for SEA regions (SG, MY, ID, PH, VN).
        """
        source_cfg = (
            load_api_config().get("http", {}).get("job_boards", {}).get("jobstreet", {}) or {}
        )
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        timeout_ms = timeout * 1000
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            iso = region_config.get("country", "").upper()
            if iso not in _SEA_CONFIG:
                continue

            site_key, domain = _SEA_CONFIG[iso]
            api_url = _api_url(domain)
            req_headers = _headers(domain)

            for title in title_filters:
                page = 1
                use_playwright_fallback = False
                while True:
                    if use_playwright_fallback:
                        stubs = _fetch_page_playwright(domain, site_key, title, page, timeout_ms)
                        if not stubs:
                            break
                        before = len(jobs)
                        for stub in stubs:
                            if stub.get("_stub"):
                                job_id = stub["_id"]
                                jobs.append(
                                    JobPosting(
                                        title=title,
                                        company="",
                                        url=_job_url(domain, job_id),
                                        posted="",
                                        location=region_config.get("location", iso),
                                        snippet="",
                                        source="JobStreet",
                                        query=f"{title} @ {region_name}",
                                        region=region_name,
                                    )
                                )
                        logger.info(
                            "[jobstreet] +%d stubs via Playwright for %r in %s page %d",
                            len(jobs) - before,
                            title,
                            region_name,
                            page,
                        )
                        break  # Playwright fallback is single-page only

                    try:
                        resp = requests.get(
                            api_url,
                            params={
                                "siteKey": site_key,
                                "keywords": title,
                                "page": page,
                                "pageSize": _PAGE_SIZE,
                                "sortMode": 1,
                            },
                            headers=req_headers,
                            timeout=timeout,
                        )
                        if resp.status_code in (403, 429, 503):
                            logger.debug(
                                "[jobstreet] %d for %r in %s; switching to Playwright",
                                resp.status_code,
                                title,
                                region_name,
                            )
                            use_playwright_fallback = True
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        logger.warning(
                            "[jobstreet] failed for %r in %s page %d: %s",
                            title,
                            region_name,
                            page,
                            exc,
                        )
                        break

                    items = (data.get("data") or {}).get("jobs") or data.get("jobs") or []
                    if not items:
                        break

                    before = len(jobs)
                    for item in items:
                        job_title = str(item.get("title") or "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue

                        advertiser = item.get("advertiser") or {}
                        company = str(advertiser.get("description") or advertiser.get("name") or "")
                        job_id = str(item.get("id") or "")
                        job_url = _job_url(domain, job_id) if job_id else ""

                        salary_obj = item.get("salary") or {}
                        salary_min = salary_obj.get("min") or salary_obj.get("minimum")
                        salary_max = salary_obj.get("max") or salary_obj.get("maximum")
                        posted = str(item.get("listingDate") or item.get("postedDate") or "")[:10]
                        teaser = strip_html(
                            str(item.get("teaser") or item.get("description") or "")
                        )
                        snippet = teaser
                        if salary_min and salary_max:
                            snippet = f"Salary: {salary_min}–{salary_max}. " + snippet

                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=company,
                                url=job_url,
                                posted=posted,
                                location=region_config.get("location", iso),
                                snippet=snippet[:3000],
                                source="JobStreet",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[jobstreet] +%d jobs for %r in %s page %d",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )

                    if len(items) < _PAGE_SIZE:
                        break
                    page += 1

        logger.info("[jobstreet] Complete: %d total jobs", len(jobs))
        return jobs
