from __future__ import annotations

import logging

from job_hunter_core.sources.ats_urls import detect_ats
from job_hunter_core.sources.ats.ashby import fetch_ashby_jobs
from job_hunter_core.sources.ats.breezy import fetch_breezy_jobs
from job_hunter_core.sources.ats.greenhouse import fetch_greenhouse_jobs
from job_hunter_core.sources.ats.hibob import fetch_hibob_jobs
from job_hunter_core.sources.ats.lever import fetch_lever_jobs
from job_hunter_core.sources.ats.personio import fetch_personio_jobs
from job_hunter_core.sources.ats.recruitee import fetch_recruitee_jobs
from job_hunter_core.sources.ats.smartrecruiters import fetch_smartrecruiters_jobs
from job_hunter_core.sources.ats.teamtailor import fetch_teamtailor_jobs
from job_hunter_core.sources.ats.workable import fetch_workable_jobs
from job_hunter_core.sources.ats.workday import fetch_workday_jobs

logger = logging.getLogger(__name__)

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
