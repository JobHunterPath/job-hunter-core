"""Caches discovered candidate URLs so broad discovery does not rediscover them.

The cache supports two formats:

  Legacy flat format (list of URL strings):
    candidate_urls:
      - https://...

  Rich format (list of objects with url + optional metadata):
    candidate_urls:
      - url: https://...
        title: "..."
        company: "..."
        posted: "..."
        snippet: "..."

Both formats are read transparently. Writes always use the flat format so the
file stays small and diff-friendly. Metadata is only used during cache
revalidation when the scraper needs to reconstruct a minimal job dict.
"""

from __future__ import annotations

import os

import yaml

from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.sources.search_providers import canonicalize_url

ROOT = str(REPO_ROOT)
CACHE_FILE = os.path.join(ROOT, "config", "discovery_cache.yml")


def _iter_cache_entries(data: dict) -> list:
    """Return raw entries from the candidate_urls list regardless of format."""
    return data.get("candidate_urls", []) or []


def load_cached_candidate_urls() -> set[str]:
    """Return the set of canonicalized URLs already seen by broad discovery."""
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    result = set()
    for entry in _iter_cache_entries(data):
        if isinstance(entry, str):
            url = entry
        elif isinstance(entry, dict):
            url = entry.get("url", "")
        else:
            continue
        if url:
            result.add(canonicalize_url(url))
    return result


def load_cached_candidate_urls_with_metadata() -> dict[str, dict]:
    """Return a mapping of canonicalized URL -> metadata dict.

    The metadata dict may be empty for flat-format entries. Keys that may be
    present: ``title``, ``company``, ``posted``, ``snippet``.

    Used by the cache revalidation fallback so it can reconstruct a minimal
    job dict without re-fetching every cached URL.
    """
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    result: dict[str, dict] = {}
    for entry in _iter_cache_entries(data):
        if isinstance(entry, str):
            canonical = canonicalize_url(entry)
            if canonical:
                result[canonical] = {}
        elif isinstance(entry, dict):
            url = entry.get("url", "")
            if not url:
                continue
            canonical = canonicalize_url(url)
            if canonical:
                result[canonical] = {
                    k: entry[k] for k in ("title", "company", "posted", "snippet") if k in entry
                }
    return result


def save_cached_candidate_urls(urls: set[str]) -> None:
    header = (
        "# Broad discovery candidate URLs already seen by the pipeline.\n"
        "# This keeps SearXNG/search API/AI discovery from rediscovering the same listings.\n\n"
    )
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(
            {"candidate_urls": sorted(urls)},
            f,
            default_flow_style=False,
            allow_unicode=True,
        )
