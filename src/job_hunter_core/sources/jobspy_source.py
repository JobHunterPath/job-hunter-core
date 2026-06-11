"""JobSpy-based job discovery via Google Jobs, Indeed, Bayt, and Glassdoor.

Falls back gracefully if python-jobspy is not installed — the rest of
the pipeline continues without it.

Source selection is derived automatically from each region's ISO country code
(the `country` field in search_config.yml regions). No per-region mapping config
is needed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from job_hunter_core.core.config import load_api_config
from job_hunter_core.core.utils import location_matches, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

# Sites that returned HTTP 403 this run — never called again until process restarts.
_DISABLED_SITES: set[str] = set()
_DISABLED_SITES_LOCK = threading.Lock()


def _is_403_block(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "403" in msg or "forbidden" in msg


def _disable_site(site: str) -> None:
    with _DISABLED_SITES_LOCK:
        if site not in _DISABLED_SITES:
            _DISABLED_SITES.add(site)
            logger.warning("[jobspy] %s disabled for this run (HTTP 403 block)", site)


# ISO 3166-1 alpha-2 → jobspy Indeed country name
_ISO_TO_INDEED: dict[str, str] = {
    "AU": "australia",
    "AT": "austria",
    "BE": "belgium",
    "BR": "brazil",
    "BH": "bahrain",
    "CA": "canada",
    "CL": "chile",
    "CN": "china",
    "CO": "colombia",
    "CR": "costarica",
    "CZ": "czechrepublic",
    "DK": "denmark",
    "EC": "ecuador",
    "EG": "egypt",
    "FI": "finland",
    "FR": "france",
    "DE": "germany",
    "GR": "greece",
    "HK": "hongkong",
    "HU": "hungary",
    "ID": "indonesia",
    "IE": "ireland",
    "IT": "italy",
    "JP": "japan",
    "KW": "kuwait",
    "LU": "luxembourg",
    "MY": "malaysia",
    "MX": "mexico",
    "MA": "morocco",
    "NL": "netherlands",
    "NZ": "newzealand",
    "NG": "nigeria",
    "NO": "norway",
    "OM": "oman",
    "PK": "pakistan",
    "PA": "panama",
    "PE": "peru",
    "PH": "philippines",
    "PL": "poland",
    "PT": "portugal",
    "QA": "qatar",
    "RO": "romania",
    "SA": "saudiarabia",
    "SG": "singapore",
    "ZA": "southafrica",
    "KR": "southkorea",
    "ES": "spain",
    "SE": "sweden",
    "CH": "switzerland",
    "TW": "taiwan",
    "TH": "thailand",
    "TR": "turkey",
    "AE": "unitedarabemirates",
    "UA": "ukraine",
    "GB": "uk",
    "US": "usa",
    "VE": "venezuela",
    "VN": "vietnam",
}

# ISO codes where Bayt (Middle East's largest job board) is relevant
_BAYT_ISO: frozenset[str] = frozenset({"QA", "BH", "OM", "AE", "SA", "KW"})


def _str(val: Any) -> str:
    """Safe string conversion — handles None and float NaN from pandas."""
    if val is None or val != val:  # val != val is True only for NaN
        return ""
    return str(val).strip()


def _row_to_job(row: Any, region_name: str) -> dict | None:
    title = _str(row.get("title"))
    url = _str(row.get("job_url"))
    if not title or not url:
        return None

    site = _str(row.get("site")).lower()
    return {
        "title": title,
        "company": _str(row.get("company")),
        "url": url,
        "posted": _str(row.get("date_posted")),
        "snippet": _str(row.get("description"))[:3000],
        "source": f"JobSpy/{site.title()}" if site else "JobSpy",
        "query": f"{title} @ {region_name}",
    }


class JobSpySource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "jobspy"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        jobspy_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobspy", {}) or {}
        return bool(jobspy_cfg.get("enabled", False))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict[str, Any],
        config: dict[str, Any],
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """
        Scrape job boards via python-jobspy for each title × region.

        Sources used per region (derived from region's ISO country code):
        - Google Jobs: always
        - Indeed: when the region's country has a known Indeed country name
        - Bayt: when the region's country is a Middle East ISO code, searched internationally
        - Glassdoor: when glassdoor_enabled is true in config
        - LinkedIn: when linkedin_enabled is true (off by default — gets blocked)

        Silently skips if python-jobspy is not installed or disabled in config.
        """
        try:
            from jobspy import scrape_jobs  # type: ignore[import]
        except ImportError:
            logger.warning("[jobspy] python-jobspy not installed — skipping JobSpy discovery")
            return []

        jobspy_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("jobspy", {}) or {}
        if not jobspy_cfg.get("enabled", False):
            return []

        hours_old = int(jobspy_cfg.get("hours_old", 72))
        results_per_query = int(jobspy_cfg.get("results_per_query", 15))
        glassdoor_enabled: bool = bool(jobspy_cfg.get("glassdoor_enabled", True))
        linkedin_enabled: bool = bool(jobspy_cfg.get("linkedin_enabled", False))
        linkedin_fetch_description: bool = bool(jobspy_cfg.get("linkedin_fetch_description", False))
        configured_sites: list[str] = list(jobspy_cfg.get("sites") or [])

        _excluded: list[str] = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []

        for region_name, region_config in enabled_regions.items():
            location = region_config.get("location", "")
            iso = region_config.get("country", "").upper()

            country_indeed = _ISO_TO_INDEED.get(iso, "")

            if configured_sites:
                sources = configured_sites
            else:
                sources = ["google"]
                if country_indeed:
                    sources.append("indeed")
                if glassdoor_enabled:
                    sources.append("glassdoor")
                if linkedin_enabled:
                    sources.append("linkedin")

            for title in title_filters:
                search_batches = [(sources, location)]
                if iso in _BAYT_ISO:
                    search_batches.append((["bayt"], ""))

                for batch_sources, scrape_location in search_batches:
                    with _DISABLED_SITES_LOCK:
                        active_sites = [s for s in batch_sources if s not in _DISABLED_SITES]

                    if not active_sites:
                        logger.debug("[jobspy] all sites in batch disabled; skipping")
                        continue

                    for site in active_sites:
                        with _DISABLED_SITES_LOCK:
                            if site in _DISABLED_SITES:
                                continue

                        logger.info(
                            "[jobspy] [%s] Searching [%s] for %r", region_name, site, title
                        )
                        try:
                            df = scrape_jobs(
                                site_name=[site],
                                search_term=title,
                                location=scrape_location,
                                results_wanted=results_per_query,
                                hours_old=hours_old,
                                country_indeed=country_indeed or "usa",
                                description_format="markdown",
                                linkedin_fetch_description=linkedin_fetch_description,
                                verbose=0,
                            )
                        except Exception as exc:
                            if _is_403_block(exc):
                                _disable_site(site)
                            else:
                                logger.warning(
                                    "[jobspy] scrape_jobs failed for %r in %r via [%s]: %s",
                                    title,
                                    scrape_location or "international",
                                    site,
                                    exc,
                                )
                            continue

                        if df is None or df.empty:
                            logger.info(
                                "[jobspy] No results for %r in %r via [%s]",
                                title,
                                scrape_location or "international",
                                site,
                            )
                            continue

                        before = len(jobs)
                        for _, row in df.iterrows():
                            row_title = _str(row.get("title"))
                            if not title_matches(row_title, title_filters, _excluded):
                                continue
                            if location:
                                row_location = _str(row.get("location"))
                                if row_location and not location_matches(row_location, location):
                                    continue
                            job_dict = _row_to_job(row, region_name)
                            if job_dict:
                                jobs.append(
                                    JobPosting(
                                        title=job_dict["title"],
                                        company=job_dict["company"],
                                        url=job_dict["url"],
                                        posted=job_dict["posted"],
                                        location="",
                                        snippet=job_dict["snippet"],
                                        source=job_dict["source"],
                                        query=job_dict["query"],
                                        region=region_name,
                                    )
                                )
                        logger.info(
                            "[jobspy] +%d jobs for %r in %r via [%s]",
                            len(jobs) - before,
                            title,
                            location,
                            site,
                        )

        logger.info("[jobspy] Complete: %d total jobs found", len(jobs))
        return jobs
