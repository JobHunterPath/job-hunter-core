"""Live source health-check for job-hunter-core.

Probes every key-free job source endpoint and reports pass/fail with HTTP
status and response time. Skips keyed sources with a note. Exits non-zero
if any registered key-free source fails.

Usage:
    python scripts/test_source_health.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field


@dataclass
class Probe:
    name: str
    method: str
    url: str
    headers: dict = field(default_factory=dict)
    body: dict | None = None
    expect_key: str | None = None  # env var that must be set; None = key-free
    expect_item_key: str | None = None  # top-level key to count items from
    expected_codes: tuple[int, ...] = (200,)  # HTTP codes treated as PASS
    note: str = ""


_PROBES: list[Probe] = [
    Probe(
        "arbeitnow",
        "GET",
        "https://www.arbeitnow.com/api/job-board-api?page=1",
        expect_item_key="data",
    ),
    Probe(
        "arbeitsagentur",
        "GET",
        "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs?was=product+manager&wo=Berlin&size=5",
        headers={"X-API-Key": "jobboerse-jobsuche"},
        expect_item_key="stellenangebote",
    ),
    Probe(
        "himalayas",
        "GET",
        "https://himalayas.app/jobs/api/search?limit=5",
        expect_item_key="jobs",
    ),
    Probe(
        "remotive",
        "GET",
        "https://remotive.com/api/remote-jobs?limit=5",
        expect_item_key="jobs",
    ),
    Probe(
        "remoteok",
        "GET",
        "https://remoteok.com/api",
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunterHealthCheck/1.0)"},
        note="first item is metadata",
    ),
    Probe(
        "jobicy",
        "GET",
        "https://jobicy.com/api/v2/remote-jobs?count=5",
        expect_item_key="jobs",
    ),
    Probe(
        "weworkremotely",
        "GET",
        "https://weworkremotely.com/remote-jobs.rss",
        note="RSS feed",
    ),
    Probe(
        "workingnomads",
        "GET",
        "https://www.workingnomads.com/api/exposed_jobs/?limit=5",
    ),
    Probe(
        "the_muse",
        "GET",
        "https://www.themuse.com/api/public/jobs?page=1",
        expect_item_key="results",
    ),
    Probe(
        "mycareersfuture",
        "GET",
        "https://api.mycareersfuture.gov.sg/v2/jobs?search=product+manager&limit=5",
        expect_item_key="results",
    ),
    Probe(
        "glints",
        "GET",
        "https://glints.com/api/jobs?keyword=product+manager&countryCode=SG",
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunterHealthCheck/1.0)"},
    ),
    Probe(
        "jobstreet",
        "GET",
        "https://www.jobstreet.com.sg/jobs/product-manager-jobs/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunterHealthCheck/1.0)"},
        expected_codes=(200, 403),
        note="403 expected outside APAC (geo-block)",
    ),
    Probe(
        "gulftalent",
        "GET",
        "https://www.gulftalent.com/jobs",
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunterHealthCheck/1.0)"},
        expected_codes=(200, 403),
        note="403 expected outside GCC (geo-block)",
    ),
    Probe(
        "jobbank",
        "GET",
        "https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring=product+manager",
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunterHealthCheck/1.0)"},
    ),
    # ATS direct endpoint probes
    Probe(
        "greenhouse (ATS)",
        "GET",
        "https://boards.greenhouse.io/anthropic",
        headers={"Accept": "application/json"},
    ),
    Probe(
        "lever (ATS)",
        "GET",
        "https://api.lever.co/v0/postings/stripe?mode=json&limit=5",
        headers={"Accept": "application/json"},
        expected_codes=(200, 404),
        note="404 if company left Lever; API up = PASS",
    ),
    Probe(
        "bamboohr (ATS)",
        "GET",
        "https://zapier.bamboohr.com/careers/list",
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 (compatible; JobHunterHealthCheck/1.0)"},
        expect_item_key="result",
    ),
    # Keyed sources — skip with note
    Probe("jooble", "GET", "", expect_key="JOOBLE_API_KEY", note="requires JOOBLE_API_KEY"),
    Probe("adzuna", "GET", "", expect_key="ADZUNA_APP_ID", note="requires ADZUNA_APP_ID + ADZUNA_API_KEY"),
    Probe("jsearch", "GET", "", expect_key="RAPIDAPI_KEY", note="requires RAPIDAPI_KEY"),
    Probe("careerjet", "GET", "", expect_key="CAREERJET_AFFID", note="requires affiliate ID"),
    Probe("reed", "GET", "", expect_key="REED_API_KEY", note="requires REED_API_KEY"),
]

_TIMEOUT = 12
_COL = {"name": 22, "status": 8, "http": 6, "time": 10, "jobs": 6}
_SEP = "=" * 80


def _count_items(data: object, key: str | None) -> int:
    if key is None:
        if isinstance(data, list):
            return len(data)
        return -1
    if isinstance(data, dict):
        val = data.get(key)
        if isinstance(val, list):
            return len(val)
        if isinstance(val, int):
            return val
    return -1


def _run_probe(probe: Probe) -> tuple[str, int | None, float, int]:
    """Returns (status_str, http_code, elapsed_ms, job_count)."""
    import requests

    if probe.expect_key and not os.environ.get(probe.expect_key):
        return "SKIP", None, 0.0, -1

    try:
        t0 = time.monotonic()
        if probe.method == "GET":
            resp = requests.get(probe.url, headers=probe.headers, timeout=_TIMEOUT)
        else:
            resp = requests.post(probe.url, json=probe.body, headers=probe.headers, timeout=_TIMEOUT)
        elapsed = (time.monotonic() - t0) * 1000

        if resp.status_code not in probe.expected_codes:
            return "FAIL", resp.status_code, elapsed, -1

        count = -1
        try:
            data = resp.json()
            count = _count_items(data, probe.expect_item_key)
        except Exception:
            pass

        return "PASS", resp.status_code, elapsed, count

    except Exception as exc:
        return f"FAIL ({exc.__class__.__name__})", None, 0.0, -1


def main() -> int:
    import datetime

    print(f"\nSource Health Check — {datetime.date.today()}")
    print(_SEP)
    header = (
        f"{'SOURCE':<{_COL['name']}} {'STATUS':<{_COL['status']}} "
        f"{'HTTP':<{_COL['http']}} {'TIME(ms)':<{_COL['time']}} {'ITEMS':<{_COL['jobs']}} NOTE"
    )
    print(header)
    print("-" * 80)

    passed = failed = skipped = 0

    for probe in _PROBES:
        status, http_code, elapsed, count = _run_probe(probe)

        http_str = str(http_code) if http_code is not None else "-"
        time_str = f"{elapsed:.0f}" if elapsed else "-"
        count_str = str(count) if count >= 0 else "-"
        note = probe.note if status == "SKIP" else (probe.note if probe.note else "")

        print(
            f"{probe.name:<{_COL['name']}} {status:<{_COL['status']}} "
            f"{http_str:<{_COL['http']}} {time_str:<{_COL['time']}} {count_str:<{_COL['jobs']}} {note}"
        )

        if status == "SKIP":
            skipped += 1
        elif status == "PASS":
            passed += 1
        else:
            failed += 1

    testable = passed + failed
    print(_SEP)
    print(f"PASS: {passed}/{testable} testable   SKIP: {skipped} (key required)   FAIL: {failed}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
