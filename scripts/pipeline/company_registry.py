"""Register directly tailored companies for future hunt runs."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CAREER_URL_PATTERNS = [
    (r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", "boards.greenhouse.io/{0}"),
    (r"jobs\.lever\.co/([^/?#]+)", "jobs.lever.co/{0}"),
    (r"jobs\.smartrecruiters\.com/([^/?#]+)", "jobs.smartrecruiters.com/{0}"),
    (r"jobs\.ashbyhq\.com/([^/?#]+)", "jobs.ashbyhq.com/{0}"),
    (r"([^/.]+)\.careers\.hibob\.com", "{0}.careers.hibob.com"),
    (r"([^/.]+)\.jobs\.personio\.de", "{0}.jobs.personio.de"),
    (r"([^/.]+)\.breezy\.hr", "{0}.breezy.hr"),
    (r"([^/.]+)\.workable\.com", "{0}.workable.com"),
    (r"([^/.]+)\.recruitee\.com", "{0}.recruitee.com"),
]


def extract_career_url(job_url: str) -> str | None:
    """Derive the ATS base/career URL from a specific job posting URL."""
    for pattern, template in CAREER_URL_PATTERNS:
        match = re.search(pattern, job_url, re.IGNORECASE)
        if match:
            return template.format(match.group(1))
    return None


def register_company(job: dict, root: str | Path) -> None:
    """Add the job's company to enabled search_config.yml regions."""
    career_url = extract_career_url(job.get("url", ""))
    if not career_url:
        logger.debug("[register] Cannot derive career URL for %s - skipping", job.get("company"))
        return

    company_name = job["company"]
    search_cfg_path = Path(root) / "config" / "search_config.yml"
    try:
        sc_data = yaml.safe_load(search_cfg_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        logger.warning("[register] search_config.yml not found - skipping scraper registration")
        return

    added_to = []
    for region_name, region_config in sc_data.get("regions", {}).items():
        if not region_config.get("enabled", True):
            continue
        companies = region_config.get("companies", [])
        existing_names = {company.get("name", "").lower() for company in companies}
        if company_name.lower() not in existing_names:
            companies.append({"name": company_name, "career_url": career_url})
            region_config["companies"] = companies
            added_to.append(region_name)

    if added_to:
        search_cfg_path.write_text(
            yaml.dump(sc_data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        logger.info(
            "[register] Added %s (%s) -> search_config.yml regions: %s",
            company_name,
            career_url,
            ", ".join(added_to),
        )
    else:
        logger.debug("[register] %s already in all enabled regions", company_name)
