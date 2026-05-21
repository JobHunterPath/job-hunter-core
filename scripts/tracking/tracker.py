"""
Tracks processed job URLs and applied titles to avoid duplicate processing across daily runs.
Uses applied_jobs.yml in the config directory as persistent storage.
"""

import os
import re
import yaml

from core.config import ROOT as REPO_ROOT

ROOT = str(REPO_ROOT)
TRACKER_FILE = os.path.join(ROOT, "config", "applied_jobs.yml")


def _title_key(company: str, title: str) -> str:
    """Normalize company+title to a stable dedup key. Strips parentheticals like (f/m/d)."""
    def normalize(s: str) -> str:
        s = s.lower()
        s = re.sub(r"\([^)]*\)", "", s)   # remove (f/m/d), (all genders), etc.
        s = re.sub(r"\s+", " ", s).strip()
        return s
    return f"{normalize(company)}::{normalize(title)}"


def load_processed() -> tuple[set[str], set[str]]:
    """Load all previously processed job URLs and applied title keys."""
    if not os.path.exists(TRACKER_FILE):
        return set(), set()
    with open(TRACKER_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    urls = set(data.get("processed", []))
    title_keys = set(data.get("applied_titles", []))
    return urls, title_keys


def save_processed(urls: set[str], title_keys: set[str]) -> None:
    """Save updated processed URLs and title keys back to file."""
    header = (
        "# Tracks all job URLs and titles already processed by the pipeline.\n"
        "# Automatically updated after each run.\n"
        "# Remove a URL/title manually to reprocess that job.\n\n"
    )
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump(
            {
                "processed": sorted(list(urls)),
                "applied_titles": sorted(list(title_keys)),
            },
            f,
            default_flow_style=False,
            allow_unicode=True,
        )


def filter_new_jobs(jobs: list[dict]) -> tuple[list[dict], set[str], set[str]]:
    """
    Removes jobs already processed in previous runs, by URL or by company+title.
    Returns (new_jobs, existing_urls, existing_title_keys).
    """
    processed_urls, applied_titles = load_processed()
    new_jobs = []
    skipped = 0

    for job in jobs:
        url = job.get("url", "")
        key = _title_key(job.get("company", ""), job.get("title", ""))

        if url and url in processed_urls:
            print(f"  [tracker] Already processed (URL): {job['title'][:50]} @ {job['company']}")
            skipped += 1
        elif key in applied_titles:
            print(f"  [tracker] Already applied (title match): {job['title'][:50]} @ {job['company']}")
            skipped += 1
        else:
            new_jobs.append(job)

    if skipped:
        print(f"[tracker] Skipped {skipped} already-processed jobs")
    print(f"[tracker] {len(new_jobs)} new jobs to process")
    return new_jobs, processed_urls, applied_titles


def mark_processed(jobs: list[dict], existing_urls: set[str], existing_titles: set[str]) -> None:
    """Add newly processed jobs to the tracker and save."""
    new_urls = {j["url"] for j in jobs if j.get("url")}
    new_keys = {
        _title_key(j["company"], j["title"])
        for j in jobs
        if j.get("company") and j.get("title")
    }

    updated_urls = existing_urls | new_urls
    updated_titles = existing_titles | new_keys

    save_processed(updated_urls, updated_titles)
    print(
        f"[tracker] Saved {len(new_urls)} new URLs, {len(new_keys)} new title keys "
        f"({len(updated_urls)} URLs, {len(updated_titles)} titles total tracked)"
    )
