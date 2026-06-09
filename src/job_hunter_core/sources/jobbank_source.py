"""Job Bank Canada (jobbank.gc.ca) — Canadian government job portal.

Free, no API key required. HTML scraping with BeautifulSoup.
Only fires for regions with country == "CA".
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import title_matches

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.jobbank.gc.ca/jobsearch/jobsearch"
_BASE_URL = "https://www.jobbank.gc.ca"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}


def fetch_jobbank_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch jobs from Job Bank Canada by scraping the HTML search results.

    Only runs for Canadian regions (country == CA).
    """
    source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobbank", {}) or {}
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        if region_config.get("country", "").upper() != "CA":
            continue

        location = region_config.get("location", "Canada")

        for title in title_filters:
            try:
                resp = requests.get(
                    _SEARCH_URL,
                    params={
                        "searchstring": title,
                        "locationstring": location,
                        "action": "search",
                        "lang": "eng",
                    },
                    headers=_HEADERS,
                    timeout=timeout,
                )
                resp.raise_for_status()
                html = resp.text
            except Exception as exc:
                logger.warning("[jobbank] failed for %r in %s: %s", title, region_name, exc)
                continue

            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all(
                "article", {"class": re.compile(r"resultcount|job-result", re.I)}
            )
            if not articles:
                # Fallback: any article with a job link
                articles = soup.select("article.found-job-offer, article[data-id]")

            before = len(jobs)
            for article in articles:
                title_tag = (
                    article.find("span", {"class": re.compile(r"noctitle|jobtitle", re.I)})
                    or article.find("h3")
                    or article.find("h2")
                )
                job_title = title_tag.get_text(strip=True) if title_tag else ""
                if not job_title:
                    continue
                if not title_matches(job_title, title_filters, excluded_title_terms):
                    continue

                company_tag = article.find(
                    class_=re.compile(r"business-title|company|employer", re.I)
                )
                company = company_tag.get_text(strip=True) if company_tag else ""

                link_tag = article.find("a", href=True)
                href = link_tag["href"] if link_tag else ""
                if href and not href.startswith("http"):
                    href = _BASE_URL + href

                location_tag = article.find(class_=re.compile(r"location|city|region", re.I))
                job_location = location_tag.get_text(strip=True) if location_tag else location

                date_tag = article.find(class_=re.compile(r"date|posted", re.I))
                posted = date_tag.get_text(strip=True) if date_tag else ""

                jobs.append(
                    {
                        "title": job_title,
                        "company": company,
                        "url": href,
                        "posted": posted,
                        "location": job_location,
                        "snippet": "",
                        "source": "JobBank Canada",
                        "query": f"{title} @ {region_name}",
                        "region": region_name,
                    }
                )
            logger.info("[jobbank] +%d jobs for %r in %s", len(jobs) - before, title, region_name)

    logger.info("[jobbank] Complete: %d total jobs", len(jobs))
    return jobs
