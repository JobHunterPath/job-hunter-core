"""
Tracks processed job URLs to avoid duplicate processing across daily runs.
Uses applied_jobs.yml in the config directory as persistent storage.
"""

from __future__ import annotations

import os

import yaml

from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.sources.search_providers import canonicalize_url

ROOT = str(REPO_ROOT)
TRACKER_FILE = os.path.join(ROOT, "config", "applied_jobs.yml")


def load_processed() -> tuple[set[str], set[str]]:
    """Load previously processed job URLs. Second return value is always empty (title-key dedup removed)."""
    if not os.path.exists(TRACKER_FILE):
        return set(), set()
    with open(TRACKER_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    urls = {canonicalize_url(u) for u in data.get("processed", []) if u}
    return urls, set()


def save_processed(urls: set[str], title_keys: set[str]) -> None:
    """Save updated processed URLs back to file. title_keys parameter retained for compatibility."""
    header = (
        "# Tracks all job URLs already processed by the pipeline.\n"
        "# Automatically updated after each run.\n"
        "# Remove a URL manually to reprocess that job.\n\n"
    )
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(
            {"processed": sorted(canonicalize_url(u) for u in urls if u)},
            f,
            default_flow_style=False,
            allow_unicode=True,
        )


def filter_new_jobs(jobs: list[dict]) -> tuple[list[dict], set[str], set[str]]:
    """
    Removes jobs already processed in previous runs by URL.
    Returns (new_jobs, existing_urls, empty_set). Third value retained for caller compatibility.
    """
    processed_urls, _ = load_processed()
    new_jobs = []
    skipped = 0

    for job in jobs:
        url = job.get("url", "")
        if url and canonicalize_url(url) in processed_urls:
            print(f"  [tracker] Already processed (URL): {job['title'][:50]} @ {job['company']}")
            skipped += 1
        else:
            new_jobs.append(job)

    if skipped:
        print(f"[tracker] Skipped {skipped} already-processed jobs")
    print(f"[tracker] {len(new_jobs)} new jobs to process")
    return new_jobs, processed_urls, set()


def mark_processed(jobs: list[dict], existing_urls: set[str], existing_titles: set[str]) -> None:
    """Add newly processed job URLs to the tracker and save. existing_titles retained for compatibility."""
    new_urls = {canonicalize_url(j["url"]) for j in jobs if j.get("url")}
    updated_urls = existing_urls | new_urls
    save_processed(updated_urls, set())
    print(f"[tracker] Saved {len(new_urls)} new URLs ({len(updated_urls)} total tracked)")
