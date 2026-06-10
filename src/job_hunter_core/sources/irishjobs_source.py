"""IrishJobs.ie — Ireland's primary job portal.

HTML scraping with BeautifulSoup. No API key required.
Only fires for regions with country == "IE".
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.irishjobs.ie/ShowResults.aspx"
_BASE_URL = "https://www.irishjobs.ie"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IE,en;q=0.9",
}


class IrishJobsSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "irishjobs"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("irishjobs", {}) or {}
        return bool(source_cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from IrishJobs.ie by scraping HTML search results.

        Only runs for Irish regions (country == IE).
        """
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("irishjobs", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            if region_config.get("country", "").upper() != "IE":
                continue

            for title in title_filters:
                try:
                    resp = requests.get(
                        _SEARCH_URL,
                        params={"Keywords": title, "action": "Search"},
                        headers=_HEADERS,
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    html = resp.text
                except Exception as exc:
                    logger.warning("[irishjobs] failed for %r in %s: %s", title, region_name, exc)
                    continue

                soup = BeautifulSoup(html, "html.parser")

                # IrishJobs uses divs/articles with class patterns for job ads
                cards = (
                    soup.find_all("div", {"class": re.compile(r"jobadvert|job-ad|job_result", re.I)})
                    or soup.find_all("article", {"class": re.compile(r"job", re.I)})
                    or soup.select("div.job-listing, li.job-item, div[data-jobid]")
                )

                before = len(jobs)
                for card in cards:
                    title_tag = (
                        card.find("a", {"class": re.compile(r"jobTitle|job-title|jobtitle", re.I)})
                        or card.find("h2")
                        or card.find("h3")
                    )
                    job_title = title_tag.get_text(strip=True) if title_tag else ""
                    if not job_title:
                        continue
                    if not title_matches(job_title, title_filters, _excluded):
                        continue

                    company_tag = card.find(class_=re.compile(r"company|employer|recruiter", re.I))
                    company = company_tag.get_text(strip=True) if company_tag else ""

                    link_tag = (
                        title_tag
                        if (title_tag and title_tag.name == "a")
                        else card.find("a", href=True)
                    )
                    href = link_tag.get("href", "") if link_tag else ""
                    if href and not href.startswith("http"):
                        href = _BASE_URL + href

                    location_tag = card.find(class_=re.compile(r"location|city|region|county", re.I))
                    job_location = location_tag.get_text(strip=True) if location_tag else "Ireland"

                    date_tag = card.find(class_=re.compile(r"date|posted|updated", re.I))
                    posted = date_tag.get_text(strip=True) if date_tag else ""

                    snippet_tag = card.find(class_=re.compile(r"description|summary|snippet", re.I))
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                    jobs.append(
                        JobPosting(
                            title=job_title,
                            company=company,
                            url=href,
                            posted=posted,
                            location=job_location,
                            snippet=snippet[:3000],
                            source="IrishJobs",
                            query=f"{title} @ {region_name}",
                            region=region_name,
                        )
                    )
                logger.info("[irishjobs] +%d jobs for %r in %s", len(jobs) - before, title, region_name)

        logger.info("[irishjobs] Complete: %d total jobs", len(jobs))
        return jobs
