"""MyCareersFuture.sg — Singapore government job portal (official REST API).

Free, no API key required. Only fires for regions with country == "SG".
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches

logger = logging.getLogger(__name__)

_API_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"
_JOB_BASE_URL = "https://www.mycareersfuture.gov.sg/job"
_PAGE_SIZE = 100


def fetch_mycareersfuture_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch jobs from MyCareersFuture.sg official REST API.

    Only runs for Singapore regions (country == SG).
    """
    source_cfg = (
        load_api_config().get("http", {}).get("job_boards", {}).get("mycareersfuture", {}) or {}
    )
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    jobs: list[dict] = []

    for region_name, region_config in enabled_regions.items():
        if region_config.get("country", "").upper() != "SG":
            continue

        for title in title_filters:
            page = 0
            while True:
                try:
                    resp = requests.get(
                        _API_URL,
                        params={"search": title, "limit": _PAGE_SIZE, "page": page},
                        timeout=timeout,
                        headers={"Accept": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning(
                        "[mycareersfuture] failed for %r in %s page %d: %s",
                        title,
                        region_name,
                        page,
                        exc,
                    )
                    break

                results = data.get("results") or []
                if not results:
                    break

                before = len(jobs)
                for item in results:
                    job_title = str(item.get("title") or "")
                    if not title_matches(job_title, title_filters, excluded_title_terms):
                        continue

                    uid = str(item.get("uuid") or "")
                    company = str(
                        (item.get("postedCompany") or {}).get("name")
                        or (item.get("hiringCompany") or {}).get("name")
                        or ""
                    )
                    description = strip_html(str(item.get("description") or ""))
                    metadata = item.get("metadata") or {}
                    dates = metadata.get("dates") or {}
                    posted = str(dates.get("posting") or dates.get("created") or "")[:10]
                    salary_obj = item.get("salary") or {}
                    salary_min = salary_obj.get("minimum")
                    salary_max = salary_obj.get("maximum")
                    location_parts = []
                    addr = item.get("address") or {}
                    if addr.get("street"):
                        location_parts.append(str(addr["street"]))
                    location_parts.append("Singapore")
                    location = ", ".join(location_parts)

                    snippet = description[:3000]
                    if salary_min and salary_max:
                        snippet = f"Salary: SGD {salary_min}–{salary_max}/mo. " + snippet

                    jobs.append(
                        {
                            "title": job_title,
                            "company": company,
                            "url": f"{_JOB_BASE_URL}/{uid}" if uid else "",
                            "posted": posted,
                            "location": location,
                            "snippet": snippet,
                            "source": "MyCareersFuture",
                            "query": f"{title} @ {region_name}",
                            "region": region_name,
                        }
                    )
                logger.info(
                    "[mycareersfuture] +%d jobs for %r in %s page %d",
                    len(jobs) - before,
                    title,
                    region_name,
                    page,
                )

                if len(results) < _PAGE_SIZE:
                    break
                page += 1

    logger.info("[mycareersfuture] Complete: %d total jobs", len(jobs))
    return jobs
