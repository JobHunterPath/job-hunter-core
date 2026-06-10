"""
ATS scrapers package.

Re-exports all public names from the ats module for backward compatibility.
`import requests` is kept here so that patch("job_hunter_core.sources.ats.requests.get", ...)
continues to work in tests.
"""

import requests  # noqa: F401 — required for test patch compatibility

from job_hunter_core.sources.ats_urls import detect_ats
from job_hunter_core.sources.ats.ashby import fetch_ashby_jobs
from job_hunter_core.sources.ats.breezy import fetch_breezy_jobs
from job_hunter_core.sources.ats.dispatch import _FETCHERS, fetch_ats_jobs
from job_hunter_core.sources.ats.greenhouse import fetch_greenhouse_jobs
from job_hunter_core.sources.ats.hibob import fetch_hibob_jobs
from job_hunter_core.sources.ats.lever import fetch_lever_jobs
from job_hunter_core.sources.ats.personio import fetch_personio_jobs
from job_hunter_core.sources.ats.recruitee import fetch_recruitee_jobs
from job_hunter_core.sources.ats.smartrecruiters import fetch_smartrecruiters_jobs
from job_hunter_core.sources.ats.teamtailor import fetch_teamtailor_jobs
from job_hunter_core.sources.ats.workable import fetch_workable_jobs
from job_hunter_core.sources.ats.workday import fetch_workday_jobs

__all__ = [
    "detect_ats",
    "fetch_ats_jobs",
    "_FETCHERS",
    "fetch_greenhouse_jobs",
    "fetch_lever_jobs",
    "fetch_smartrecruiters_jobs",
    "fetch_workable_jobs",
    "fetch_ashby_jobs",
    "fetch_hibob_jobs",
    "fetch_personio_jobs",
    "fetch_recruitee_jobs",
    "fetch_breezy_jobs",
    "fetch_teamtailor_jobs",
    "fetch_workday_jobs",
]
