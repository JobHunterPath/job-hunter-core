"""Caches discovered candidate URLs so broad discovery does not rediscover them."""

import os
import yaml

from core.config import ROOT as REPO_ROOT
from sources.search_providers import canonicalize_url

ROOT = str(REPO_ROOT)
CACHE_FILE = os.path.join(ROOT, "config", "discovery_cache.yml")


def load_cached_candidate_urls() -> set[str]:
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        canonicalize_url(url)
        for url in data.get("candidate_urls", [])
        if url
    }


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
