"""Thin policy wrapper functions delegating to JobPolicy."""

from __future__ import annotations

from job_hunter_core.sources.job_policy import JobPolicy


def is_valid_job_url(url: str) -> bool:
    """Return False for root/listing pages that are not individual job postings."""
    return JobPolicy({}).is_valid_job_url(url)


def is_excluded_url(url: str, config: dict) -> bool:
    """Return True when caller-configured URL patterns identify non-posting pages."""
    return JobPolicy(config).is_excluded_url(url)


def is_stale_posting(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_stale_posting(title, snippet)


def is_too_senior(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_too_senior(title, snippet)


def is_excluded(snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_excluded_industry(snippet)


def is_german(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_german(title, snippet)


def is_excluded_language(title: str, snippet: str, config: dict) -> bool:
    return JobPolicy(config).is_excluded_language(title, snippet)
