"""We Work Remotely RSS source — no key required.

Public RSS feed: https://weworkremotely.com/remote-jobs.rss
Uses stdlib xml.etree.ElementTree — no extra dependency.
WWR item titles are formatted as "Company Name: Job Title".
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches

logger = logging.getLogger(__name__)

_RSS_URL = "https://weworkremotely.com/remote-jobs.rss"


def _parse_rfc2822(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def fetch_weworkremotely_jobs(
    title_filters: list[str],
    enabled_regions: dict,
    config: dict,
) -> list[dict]:
    """Fetch remote jobs from We Work Remotely's public RSS feed."""
    source_cfg = (
        load_api_config().get("http", {}).get("job_boards", {}).get("weworkremotely", {}) or {}
    )
    if not source_cfg.get("enabled", True):
        return []

    timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
    first_region = next(iter(enabled_regions), "")

    logger.info("[weworkremotely] Fetching RSS feed")
    try:
        resp = requests.get(_RSS_URL, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        logger.warning("[weworkremotely] request/parse failed: %s", exc)
        return []

    jobs: list[dict] = []
    for item in root.iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        # WWR titles: "Company Name: Job Title"
        if ": " in raw_title:
            company, job_title = raw_title.split(": ", 1)
            company = company.strip()
            job_title = job_title.strip()
        else:
            company = ""
            job_title = raw_title

        if not title_matches(job_title, title_filters, excluded_title_terms):
            continue

        url = (item.findtext("link") or "").strip()
        pub_date = _parse_rfc2822(item.findtext("pubDate") or "")
        description = strip_html(item.findtext("description") or "")

        jobs.append(
            {
                "title": job_title,
                "company": company,
                "url": url,
                "posted": pub_date,
                "location": "Remote",
                "snippet": description[:3000],
                "source": "WeWorkRemotely",
                "query": job_title,
                "region": first_region,
            }
        )

    logger.info("[weworkremotely] %d jobs matched after filtering", len(jobs))
    return jobs
