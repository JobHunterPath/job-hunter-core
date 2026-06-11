"""
Weekly job: discovers new companies via an LLM + search provider fallbacks,
validates their career pages exist, and adds them to search_config.yml regions.
Deduplicates against existing entries automatically.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Any
from urllib.parse import urlparse

import yaml

from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.core.llm_client import get_llm_client
from job_hunter_core.core.llm_utils import get_llm_role_settings
from job_hunter_core.core.utils import url_is_alive
from job_hunter_core.sources.adzuna_source import AdzunaSource
from job_hunter_core.sources.arbeitsagentur_source import ArbeitsagenturSource
from job_hunter_core.sources.ats_urls import extract_career_url
from job_hunter_core.sources.himalayas_source import HimalayasSource
from job_hunter_core.sources.job_boards import ArbeitnowSource, JSearchSource
from job_hunter_core.sources.jobspy_source import JobSpySource
from job_hunter_core.sources.jooble_source import JoobleSource
from job_hunter_core.sources.search_providers import (
    discover_ats_jobs_by_search,
    search_career_urls,
    search_web,
)

ROOT = str(REPO_ROOT)
SEARCH_CONFIG_FILE = os.path.join(ROOT, "config", "search_config.yml")

# ATS URL patterns and the canonical career_url format to store in search_config.yml.
# Order matters: more specific patterns first.
ATS_PATTERNS = [
    (r"boards\.greenhouse\.io/([^/?#\s]+)", "boards.greenhouse.io/{slug}"),
    (r"job-boards\.greenhouse\.io/([^/?#\s]+)", "job-boards.greenhouse.io/{slug}"),
    (r"jobs\.lever\.co/([^/?#\s]+)", "jobs.lever.co/{slug}"),
    (r"apply\.workable\.com/([^/?#\s]+)", "apply.workable.com/{slug}"),
    (r"jobs\.ashbyhq\.com/([^/?#\s]+)", "jobs.ashbyhq.com/{slug}"),
    (r"jobs\.smartrecruiters\.com/([^/?#\s]+)", "jobs.smartrecruiters.com/{slug}"),
    # Subdomain-based ATS: slug is the company subdomain
    (r"([^./]+)\.careers\.hibob\.com", "{slug}.careers.hibob.com"),
    (r"([^./]+)\.jobs\.personio\.de", "{slug}.jobs.personio.de"),
    (r"([^./]+)\.recruitee\.com", "{slug}.recruitee.com"),
    # jobs.personio.com uses path-based slugs
    (r"jobs\.personio\.com/([^/?#\s]+)", "jobs.personio.com/{slug}"),
]

CAREER_PATH_PATTERNS = ["/careers", "/jobs", "/work-with-us", "/join-us"]
GENERIC_ATS_SLUGS = {
    "jobs",
    "job",
    "careers",
    "career",
    "apply",
    "search",
    "positions",
    "openings",
}
PATH_BASED_ATS_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
    "apply.workable.com",
    "jobs.ashbyhq.com",
    "jobs.personio.com",
}
DEFAULT_DISCOVERY_MAX_WORKERS = 10
DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS = 1800
DEFAULT_DISCOVERY_RESERVE_SECONDS = 600
DEFAULT_DISCOVERY_OVERLAP_SCOPE = "new_only"

_PROMPT_TEMPLATE = (
    "List 10 companies based in {location} (or with a significant {location} office) "
    "in the {sector} sector. Requirements:\n"
    "- English as primary working language\n"
    "- Known to hire these roles: {job_titles}\n"
    "- NOT companies in these industries: {excluded_industries}\n"
    "- NOT already in this list: {{existing}}\n\n"
    "Return ONLY a valid JSON array of company name strings. "
    "No explanation, no markdown, no code fences."
)


def _normalize_sectors(sectors: list, location: str) -> list[str]:
    normalized = []
    for sector in sectors:
        value = sector.get("sector") if isinstance(sector, dict) else sector
        if not isinstance(value, str) or not value.strip():
            continue
        normalized.append(value.format(location=location).strip())
    return normalized


def _interpolate_sectors(
    sectors: list, location: str, job_titles: list[str], excluded_industries: str
) -> list[dict[str, str]]:
    title_text = ", ".join(job_titles)
    return [
        {
            "sector": sector,
            "prompt": _PROMPT_TEMPLATE.format(
                location=location,
                sector=sector,
                job_titles=title_text,
                excluded_industries=excluded_industries,
            ),
        }
        for sector in _normalize_sectors(sectors, location)
    ]


def load_companies() -> tuple[list[dict], set[str]]:
    with open(SEARCH_CONFIG_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    companies = []
    excluded = {e.lower() for e in data.get("excluded_companies", [])}

    # Collect all companies from all regions for deduplication purposes
    seen = set()
    for region in data.get("regions", {}).values():
        for c in region.get("companies", []):
            key = (c["name"].lower(), c["career_url"].lower())
            if key not in seen:
                seen.add(key)
                companies.append({"name": c["name"], "career_url": c["career_url"]})

    return companies, excluded


def _discovery_settings(search_config: dict) -> dict:
    cfg = search_config.get("discovery", {}) or {}
    return {
        "max_workers": max(1, int(cfg.get("max_workers", DEFAULT_DISCOVERY_MAX_WORKERS))),
        "total_timeout_seconds": max(
            1,
            int(cfg.get("total_timeout_seconds", DEFAULT_DISCOVERY_TOTAL_TIMEOUT_SECONDS)),
        ),
        "reserve_seconds": max(
            0, int(cfg.get("reserve_seconds", DEFAULT_DISCOVERY_RESERVE_SECONDS))
        ),
        "overlap_scope": cfg.get("overlap_scope", DEFAULT_DISCOVERY_OVERLAP_SCOPE),
    }


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _deadline_reached(deadline: float) -> bool:
    return _remaining_seconds(deadline) <= 0


def _run_parallel_until_deadline(
    items: list, worker: Any, max_workers: int, deadline: float, label: str
) -> tuple[list, bool]:
    results = []
    if not items or _deadline_reached(deadline):
        if items:
            print(f"[discover] Deadline reached before {label}; skipping {len(items)} item(s)")
        return results, _deadline_reached(deadline)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    try:
        for item in items:
            if _deadline_reached(deadline):
                print(f"[discover] Deadline reached while submitting {label}; stopping submissions")
                break
            futures[executor.submit(worker, item)] = item

        if not futures:
            return results, _deadline_reached(deadline)

        try:
            for future in as_completed(futures, timeout=_remaining_seconds(deadline)):
                item = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    print(f"[discover] {label} failed for {item}: {e}")
                if _deadline_reached(deadline):
                    print(
                        f"[discover] Deadline reached while collecting {label}; saving partial results"
                    )
                    break
        except TimeoutError:
            print(f"[discover] Deadline reached during {label}; saving partial results")

        timed_out = any(not future.done() for future in futures)
        for future in futures:
            if not future.done():
                future.cancel()
        return results, timed_out or _deadline_reached(deadline)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def has_jobs_in_location(company_name: str, region_config: dict) -> bool:
    """Check if a company has job postings in a specific location."""
    location = region_config.get("location", "")
    job_titles = region_config.get("job_titles", [])
    queries = [
        f'"{company_name}" "{location}" "{title}" careers jobs' for title in (job_titles or ["job"])
    ]
    queries.extend(
        f'"{company_name}" "{location}" {site}'
        for site in (
            "site:jobs.lever.co",
            "site:boards.greenhouse.io",
            "site:jobs.ashbyhq.com",
            "site:jobs.smartrecruiters.com",
        )
    )
    try:
        for query in queries:
            results = search_web(query, region_config, count=3)
            for result in results:
                url = result.get("url", "").lower()
                if company_name.lower() in url and (
                    location.lower() in url or "jobs" in url or "careers" in url
                ):
                    return True
    except Exception as e:
        print(f"  [check] Error checking {company_name} in {location}: {e}")
    return False


def add_company_to_region(search_config: dict, region_name: str, company: dict) -> None:
    """Add a company to a region if not already present."""
    if region_name not in search_config.get("regions", {}):
        return
    region = search_config["regions"][region_name]
    companies = region.get("companies", [])
    if not any(c["name"].lower() == company["name"].lower() for c in companies):
        companies.append({"name": company["name"], "career_url": company["career_url"]})
        region["companies"] = companies
        print(f"  [auto-add] Added {company['name']} to region {region_name}")


def save_search_config(search_config: dict) -> None:
    """Save the updated search_config.yml."""
    with open(SEARCH_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(search_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_existing_names(companies: list[dict]) -> set[str]:
    return {c["name"].lower() for c in companies}


def get_existing_urls(companies: list[dict]) -> set[str]:
    return {c["career_url"].lower() for c in companies}


def discover_company_names(
    existing: list[dict],
    location: str,
    job_titles: list[str],
    sectors: list,
    excluded_industries: str,
) -> list[str]:
    """Run one LLM query per sector and combine the results."""
    existing_names = ", ".join(c["name"] for c in existing[:60])
    seen: set[str] = set()
    all_names: list[str] = []

    for spec in _interpolate_sectors(sectors, location, job_titles, excluded_industries):
        prompt = spec["prompt"].format(existing=existing_names)
        print(f"[discover] Querying sector: {spec['sector']}...")
        try:
            settings = get_llm_role_settings("discovery")
            raw = get_llm_client("discovery").complete(
                user=prompt,
                model=settings.model,
                max_tokens=settings.max_tokens,
            )
            names = json.loads(raw)
            added = 0
            for name in names:
                if isinstance(name, str) and name.lower() not in seen:
                    seen.add(name.lower())
                    all_names.append(name)
                    added += 1
            print(f"  → {added} new suggestions")
        except Exception as e:
            print(f"  [discover] Sector '{spec['sector']}' failed: {e}")

    return all_names


def _career_url_from_job_url(job_url: str) -> str:
    ats_url = extract_career_url(job_url)
    if ats_url:
        return ats_url

    for pattern, template in ATS_PATTERNS:
        match = re.search(pattern, job_url)
        if match:
            return template.format(slug=match.group(1).rstrip("/"))

    parsed = urlparse(job_url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    base_path = f"/{parts[0]}" if parts else ""
    return f"{parsed.netloc}{base_path}" if parsed.netloc else job_url


def _career_url_is_specific(career_url: str) -> bool:
    """Reject generic ATS roots that cause false duplicates across companies."""
    candidate = career_url if "://" in career_url else f"https://{career_url}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.strip("/").split("/") if part]

    if host in PATH_BASED_ATS_HOSTS:
        return bool(parts and parts[0].lower() not in GENERIC_ATS_SLUGS)
    if host.endswith(".jobs.personio.de"):
        return host.split(".jobs.personio.de", 1)[0] not in GENERIC_ATS_SLUGS
    if host.endswith(".recruitee.com"):
        return host.split(".recruitee.com", 1)[0] not in GENERIC_ATS_SLUGS
    if host.endswith(".careers.hibob.com"):
        return host.split(".careers.hibob.com", 1)[0] not in GENERIC_ATS_SLUGS
    if host.endswith(".teamtailor.com"):
        return host.split(".teamtailor.com", 1)[0] not in GENERIC_ATS_SLUGS
    if host.endswith(".breezy.hr"):
        return host.split(".breezy.hr", 1)[0] not in GENERIC_ATS_SLUGS
    if host.endswith(".myworkdayjobs.com"):
        return host.split(".myworkdayjobs.com", 1)[0] not in GENERIC_ATS_SLUGS
    return bool(host)


def _is_ats_career_url(career_url: str) -> bool:
    candidate = career_url if "://" in career_url else f"https://{career_url}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    return host in PATH_BASED_ATS_HOSTS or any(
        host.endswith(suffix)
        for suffix in (
            ".jobs.personio.de",
            ".recruitee.com",
            ".careers.hibob.com",
            ".teamtailor.com",
            ".breezy.hr",
            ".myworkdayjobs.com",
        )
    )


def _career_url_has_job_signal(
    company: dict, region_config: dict, title_filters: list[str]
) -> bool:
    """Validate custom career pages before auto-add."""
    career_url = str(company.get("career_url") or "")
    if not _career_url_is_specific(career_url):
        return False
    if _is_ats_career_url(career_url):
        url = career_url if "://" in career_url else f"https://{career_url}"
        alive = url_is_alive(url, timeout=8)
        if not alive:
            print(f"  [validate] ATS URL unreachable (dead slug?): {career_url}")
        return alive
    try:
        from job_hunter_core.sources.career_pages import extract_career_page_jobs

        candidate = {
            "name": company.get("name", ""),
            "career_url": career_url,
            "location": region_config.get("location", ""),
        }
        return bool(extract_career_page_jobs(candidate, title_filters, []))
    except Exception as exc:
        print(f"  [validate] Career page validation failed for {company.get('name')}: {exc}")
        return False


def discover_company_candidates(
    search_config: dict,
    region_name: str,
    region_config: dict,
    job_titles: list[str],
) -> list[dict]:
    """Discover companies from real ATS postings for the configured titles and region."""
    exclusion_rules = search_config.get("exclusion_rules", {}) or {}
    excluded_title_terms = exclusion_rules.get("excluded_title_terms", []) or []
    region_titles = region_config.get("job_titles", []) or []
    title_filters = list(dict.fromkeys([*job_titles, *region_titles]))
    if not title_filters:
        return []

    jobs = discover_ats_jobs_by_search(
        title_filters=title_filters,
        regions={region_name: region_config},
        excluded_title_terms=excluded_title_terms,
        ats_discovery_cfg=search_config.get("ats_discovery", {}),
    )

    seen_names: set[str] = set()
    candidates = []
    for job in jobs:
        name = str(job.get("company") or "").strip()
        url = str(job.get("url") or "").strip()
        if not name or not url:
            continue
        career_url = _career_url_from_job_url(url)
        if not _career_url_is_specific(career_url):
            continue
        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        candidates.append({"name": name, "career_url": career_url})
    return candidates


def discover_company_names_from_job_sources(
    search_config: dict,
    region_name: str,
    region_config: dict,
    job_titles: list[str],
) -> list[str]:
    """Discover company names from the existing broad job-board search sources."""
    exclusion_rules = search_config.get("exclusion_rules", {}) or {}
    excluded_title_terms = exclusion_rules.get("excluded_title_terms", []) or []
    region_titles = region_config.get("job_titles", []) or []
    title_filters = list(dict.fromkeys([*job_titles, *region_titles]))
    if not title_filters:
        return []

    names: list[str] = []
    seen: set[str] = set()

    def _add_jobs(jobs: list[dict]) -> None:
        for job in jobs:
            name = str(job.get("company") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            names.append(name)

    enabled_region = {region_name: region_config}
    _add_jobs(
        [
            jp.to_dict()
            for jp in ArbeitnowSource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )
    _add_jobs(
        [
            jp.to_dict()
            for jp in JSearchSource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )
    _add_jobs(
        [
            jp.to_dict()
            for jp in AdzunaSource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )
    _add_jobs(
        [
            jp.to_dict()
            for jp in JoobleSource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )
    _add_jobs(
        [
            jp.to_dict()
            for jp in JobSpySource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )
    _add_jobs(
        [
            jp.to_dict()
            for jp in ArbeitsagenturSource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )
    _add_jobs(
        [
            jp.to_dict()
            for jp in HimalayasSource().fetch(
                title_filters,
                enabled_region,
                search_config,
                excluded_title_terms=excluded_title_terms,
            )
        ]
    )

    return names


def brave_search(query: str, count: int = 5, region_config: dict | None = None) -> list[dict]:
    """Compatibility wrapper; now uses the full search provider chain."""
    return search_web(region_config=region_config or {}, query=query, count=count)


def find_career_url(company_name: str, existing_urls: set[str], region_config: dict) -> dict | None:
    """
    Search provider fallbacks for the company's career page.

    Two passes:
      1. ATS-targeted query across all supported platforms.
      2. Broad career/jobs query for companies on custom domains.

    Returns a dict with name + career_url if found, None otherwise.
    """
    try:
        results = search_career_urls(company_name, region_config, count=7)
    except Exception as e:
        print(f"  [search] Error searching for {company_name}: {e}")
        results = []

    for result in results:
        url = result.get("url", "")

        for pattern, template in ATS_PATTERNS:
            match = re.search(pattern, url)
            if match:
                slug = match.group(1).rstrip("/")
                career_url = template.format(slug=slug)
                if career_url.lower() not in existing_urls and _career_url_is_specific(career_url):
                    print(f"  [found] {company_name} -> {career_url} (ATS)")
                    return {"name": company_name, "career_url": career_url}

        for path in CAREER_PATH_PATTERNS:
            if path in url.lower():
                domain_match = re.match(r"https?://([^/]+)", url)
                if domain_match:
                    domain = domain_match.group(1)
                    career_url = f"{domain}{path}"
                    if (
                        career_url.lower() not in existing_urls
                        and _career_url_is_specific(career_url)
                        and url_is_alive(f"https://{career_url}", timeout=8)
                    ):
                        print(f"  [found] {company_name} -> {career_url} (direct)")
                        return {"name": company_name, "career_url": career_url}

    print(f"  [miss] No career page found for {company_name}")
    return None


def run(region: str | None = None) -> None:
    print("\n" + "=" * 50)
    print("Weekly Company Discovery")
    print("=" * 50 + "\n")

    existing, excluded = load_companies()
    existing_names = get_existing_names(existing)
    existing_urls = get_existing_urls(existing)
    print(f"[discover] Currently tracking {len(existing)} companies")
    print(f"[discover] Excluding {len(excluded)} companies: {sorted(excluded)}")

    # Load search_config for region info and potential updates
    search_config = {}
    if os.path.exists(SEARCH_CONFIG_FILE):
        with open(SEARCH_CONFIG_FILE, encoding="utf-8") as f:
            search_config = yaml.safe_load(f) or {}

    all_regions = search_config.get("regions", {}) or {}
    regions = {
        k: v
        for k, v in all_regions.items()
        if v.get("enabled", True) and (region is None or k == region)
    }
    job_titles = search_config.get("global_search", {}).get("job_titles", [])
    sectors = search_config.get("discovery", {}).get("sectors", [])
    settings = _discovery_settings(search_config)
    started_at = time.monotonic()
    effective_timeout = max(
        1,
        settings["total_timeout_seconds"] - settings["reserve_seconds"],
    )
    deadline = started_at + effective_timeout
    excluded_industries = ", ".join(
        search_config.get("exclusion_rules", {}).get("excluded_industries", [])
    )

    if not regions:
        print("[discover] No enabled regions found in search_config.yml. Nothing to discover.")
        return
    if not job_titles:
        print("[discover] global_search.job_titles is empty. Nothing to discover.")
        return

    for region_config in regions.values():
        region_titles = region_config.get("job_titles", []) or []
        region_config["job_titles"] = list(dict.fromkeys([*job_titles, *region_titles]))

    region_discoveries = {}  # Track which region discovered which companies
    discovered_entries: list[tuple[str, dict]] = []
    dirty = False
    deadline_hit = False

    print(
        "[discover] Runtime budget: "
        f"{effective_timeout}s discovery work + {settings['reserve_seconds']}s reserve; "
        f"max_workers={settings['max_workers']}; overlap_scope={settings['overlap_scope']}"
    )

    for region_name, region_config in regions.items():
        if _deadline_reached(deadline):
            deadline_hit = True
            print(
                "[discover] Deadline reached before next region; saving partial discovery results"
            )
            break

        location = region_config.get("location", region_name.title())
        print(f"\n[discover] Discovering companies for region: {region_name} ({location})")

        ats_entries = []
        if not deadline_hit and not _deadline_reached(deadline):
            print(f"[discover] Searching ATS postings for {region_name} (deterministic mode)...")
            try:
                ats_entries = discover_company_candidates(
                    search_config,
                    region_name,
                    region_config,
                    job_titles,
                )
                print(
                    f"[discover] ATS posting discovery found {len(ats_entries)} candidate(s) "
                    f"(source: real postings, no LLM names used)."
                )
            except Exception as e:
                print(f"[discover] ATS discovery failed for {region_name}: {e}")

        job_source_names = []
        if not deadline_hit and not _deadline_reached(deadline):
            print(f"[discover] Searching existing job sources for {region_name} companies...")
            try:
                job_source_names = discover_company_names_from_job_sources(
                    search_config,
                    region_name,
                    region_config,
                    job_titles,
                )
                print(
                    f"[discover] Existing job sources found {len(job_source_names)} "
                    "company name(s)."
                )
            except Exception as e:
                print(f"[discover] Existing job-source discovery failed for {region_name}: {e}")

        suggested = []
        sector_names = ", ".join(_normalize_sectors(sectors, location))
        if sector_names and not deadline_hit and not _deadline_reached(deadline):
            print(f"[discover] Querying LLM across sectors: {sector_names}")
            suggested = discover_company_names(
                existing, location, region_config["job_titles"], sectors, excluded_industries
            )
            print(f"[discover] LLM suggested {len(suggested)} companies: {suggested}\n")
        elif not sector_names:
            print("[discover] No LLM sectors configured; running in deterministic ATS-only mode.")

        suggested = list(dict.fromkeys([*job_source_names, *suggested]))
        new_names = [
            name
            for name in suggested
            if name.lower() not in existing_names and name.lower() not in excluded
        ]

        skipped_excluded = [name for name in suggested if name.lower() in excluded]
        if skipped_excluded:
            print(f"[discover] Excluded by exclusion list: {skipped_excluded}")

        print(f"[discover] {len(new_names)} LLM suggestions not yet tracked: {new_names}\n")

        new_entries = []
        existing_urls_snapshot = set(existing_urls)

        def _lookup_name(
            name: str, _urls=existing_urls_snapshot, _cfg=region_config
        ) -> dict | None:
            print(f"[discover] Looking up: {name}")
            return find_career_url(name, _urls, _cfg)

        lookup_results, lookup_timed_out = _run_parallel_until_deadline(
            new_names,
            _lookup_name,
            settings["max_workers"],
            deadline,
            f"career URL lookup for {region_name}",
        )
        if lookup_timed_out:
            deadline_hit = True

        job_source_name_keys = {name.lower() for name in job_source_names}
        job_source_entries = [
            entry
            for entry in lookup_results
            if entry and entry["name"].lower() in job_source_name_keys
        ]
        llm_entries = [
            entry
            for entry in lookup_results
            if entry and entry["name"].lower() not in job_source_name_keys
        ]

        # Surface origin so users can see where companies came from.
        combined_entries = list(llm_entries)
        combined_entries.extend(job_source_entries)
        combined_entries.extend(ats_entries)
        print(
            f"[discover] Company origin summary for {region_name}: "
            f"llm={len(llm_entries)}, job_sources={len(job_source_entries)}, "
            f"job_source_names={len(job_source_names)}, "
            f"ats_postings={len(ats_entries)}, "
            f"combined={len(combined_entries)}"
        )

        for entry in sorted(combined_entries, key=lambda e: e["name"].lower()):
            entry_name = entry["name"].lower()
            entry_url = entry["career_url"].lower()
            valid_titles = region_config.get("job_titles", []) or job_titles
            if (
                entry_name in existing_names
                or entry_url in existing_urls
                or entry_name in excluded
                or not _career_url_is_specific(entry["career_url"])
                or not _career_url_has_job_signal(entry, region_config, valid_titles)
            ):
                continue
            new_entries.append(entry)
            existing_urls.add(entry_url)
            existing_names.add(entry_name)
            region_discoveries[entry_name] = region_name
            discovered_entries.append((region_name, entry))

        if new_entries:
            print(f"[discover] Added {len(new_entries)} new companies for {region_name}:")
            for entry in new_entries:
                print(f"  + {entry['name']} -> {entry['career_url']}")
                # Add to the region's companies list
                region_companies = search_config["regions"][region_name].get("companies", [])
                if not any(c["name"].lower() == entry["name"].lower() for c in region_companies):
                    region_companies.append(
                        {"name": entry["name"], "career_url": entry["career_url"]}
                    )
                    search_config["regions"][region_name]["companies"] = region_companies
                    dirty = True

        if dirty:
            save_search_config(search_config)

        if deadline_hit:
            print("[discover] Deadline reached; saving partial discovery results")
            break

    # Automatic region distribution for overlaps
    if regions and not deadline_hit and not _deadline_reached(deadline):
        print("\n[discover] Checking for overlaps in other regions...")
        overlap_scope = settings["overlap_scope"]
        if overlap_scope != DEFAULT_DISCOVERY_OVERLAP_SCOPE:
            print(
                f"[discover] Unsupported overlap_scope={overlap_scope!r}; using {DEFAULT_DISCOVERY_OVERLAP_SCOPE!r}"
            )

        overlap_items = [
            (company, source_region, other_region, other_config)
            for source_region, company in discovered_entries
            for other_region, other_config in regions.items()
            if other_region != source_region
        ]

        def _check_overlap(item):
            company, _source_region, other_region, other_config = item
            return item if has_jobs_in_location(company["name"], other_config) else None

        overlap_results, overlap_timed_out = _run_parallel_until_deadline(
            overlap_items,
            _check_overlap,
            settings["max_workers"],
            deadline,
            "overlap checks",
        )
        if overlap_timed_out:
            deadline_hit = True

        for result in overlap_results:
            if not result:
                continue
            company, _source_region, other_region, _other_config = result
            before_count = len(search_config["regions"][other_region].get("companies", []))
            add_company_to_region(search_config, other_region, company)
            after_count = len(search_config["regions"][other_region].get("companies", []))
            dirty = dirty or after_count > before_count
    elif regions:
        deadline_hit = True
        print("[discover] Deadline reached before overlap checks; saving partial discovery results")

    if not any(search_config["regions"][r].get("companies", []) for r in regions.keys()):
        print("\n[discover] No new companies to add.")
        return

    # Save updated search_config
    if dirty or deadline_hit:
        save_search_config(search_config)
    if deadline_hit:
        print("[discover] Deadline reached; saved partial discovery results")

    print(
        f"\n[discover] Discovery complete. search_config.yml now has companies across {len(regions)} regions"
    )


if __name__ == "__main__":
    run()
