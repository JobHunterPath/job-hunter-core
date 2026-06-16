"""Shared ATS URL parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class AtsCareerPattern:
    name: str
    pattern: str
    career_template: str


ATS_CAREER_PATTERNS: tuple[AtsCareerPattern, ...] = (
    AtsCareerPattern(
        "greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)", "boards.greenhouse.io/{0}"
    ),
    AtsCareerPattern("lever", r"jobs\.lever\.co/([^/?#]+)", "jobs.lever.co/{0}"),
    AtsCareerPattern("bamboohr", r"([^/.]+)\.bamboohr\.com", "{0}.bamboohr.com"),
    AtsCareerPattern(
        "smartrecruiters", r"jobs\.smartrecruiters\.com/([^/?#]+)", "jobs.smartrecruiters.com/{0}"
    ),
    AtsCareerPattern("workable", r"apply\.workable\.com/([^/?#]+)", "apply.workable.com/{0}"),
    AtsCareerPattern("ashby", r"jobs\.ashbyhq\.com/([^/?#]+)", "jobs.ashbyhq.com/{0}"),
    AtsCareerPattern("hibob", r"([^/.]+)\.careers\.hibob\.com", "{0}.careers.hibob.com"),
    AtsCareerPattern("personio", r"([^/.]+)\.jobs\.personio\.de", "{0}.jobs.personio.de"),
    AtsCareerPattern("breezy", r"([^/.]+)\.breezy\.hr", "{0}.breezy.hr"),
    AtsCareerPattern("recruitee", r"([^/.]+)\.recruitee\.com", "{0}.recruitee.com"),
    AtsCareerPattern("teamtailor", r"([^/.]+)\.teamtailor\.com", "{0}.teamtailor.com"),
    AtsCareerPattern("workday", r"([^/]+\.myworkdayjobs\.com/[^/?#]+)", "{0}"),
)

_DIRECT_ATS_NAMES = {
    "greenhouse",
    "lever",
    "smartrecruiters",
    "workable",
    "ashby",
    "hibob",
    "personio",
    "breezy",
    "recruitee",
    "teamtailor",
    "workday",
    "bamboohr",
}


def _without_scheme(url: str) -> str:
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def detect_ats(career_url: str) -> tuple[str, str] | None:
    """Return (ats_name, slug) for supported direct ATS career URLs."""
    normalized = _without_scheme(career_url)
    for ats in ATS_CAREER_PATTERNS:
        if ats.name not in _DIRECT_ATS_NAMES:
            continue
        match = re.search(ats.pattern, normalized, re.IGNORECASE)
        if match:
            return ats.name, match.group(1)
    return None


def extract_career_url(job_url: str) -> str | None:
    """Derive the ATS base/career URL from a specific job posting URL."""
    normalized = _without_scheme(job_url)
    for ats in ATS_CAREER_PATTERNS:
        match = re.search(ats.pattern, normalized, re.IGNORECASE)
        if match:
            return ats.career_template.format(match.group(1))
    return None


def company_slug_from_url(url: str) -> str | None:
    """Return the most likely company slug embedded in an ATS or career URL."""
    normalized = _without_scheme(url)
    for ats in ATS_CAREER_PATTERNS:
        match = re.search(ats.pattern, normalized, re.IGNORECASE)
        if match:
            if ats.name == "workday":
                return match.group(1).split(".", 1)[0]
            return match.group(1)

    parsed = urlparse(f"https://{normalized}")
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.startswith(("careers.", "jobs.")) and len(parsed.netloc.split(".")) > 2:
        return parsed.netloc.split(".")[1]
    if parts and re.search(r"\b(careers?|jobs?)\b", parsed.netloc, re.IGNORECASE):
        return parts[0]
    return None


def company_name_from_url(url: str) -> str | None:
    slug = company_slug_from_url(url)
    if not slug:
        return None
    return slug.replace("-", " ").replace("_", " ").strip().title()
