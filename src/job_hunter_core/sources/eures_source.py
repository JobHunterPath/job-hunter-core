"""EURES — European Employment Services job portal (unofficial public REST API).

Covers 27 EU member states plus Norway, Iceland, and Liechtenstein.
Free, no API key required. Only fires for regions whose country code is in the EU/EEA set.
"""

from __future__ import annotations

import logging

import requests

from job_hunter_core.core.config import get_timeout, load_api_config
from job_hunter_core.core.utils import strip_html, title_matches
from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)

_API_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
_PAGE_SIZE = 50

# EU member states + EEA countries supported by EURES
_EU_EEA_CODES: frozenset[str] = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HR",
        "HU",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
        "IS",
        "LI",
        "NO",  # EEA non-EU
    }
)


class EURESSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "eures"

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("eures", {}) or {}
        return bool(source_cfg.get("enabled", True))

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        """Fetch jobs from the EURES public job search API.

        Only runs for EU/EEA regions (country code in _EU_EEA_CODES).
        """
        source_cfg = load_api_config().get("http", {}).get("job_boards", {}).get("eures", {}) or {}
        if not source_cfg.get("enabled", True):
            return []

        timeout = int(source_cfg.get("timeout_seconds") or get_timeout("job_boards"))
        _excluded = (
            excluded_title_terms
            if excluded_title_terms is not None
            else config.get("exclusion_rules", {}).get("excluded_title_terms", []) or []
        )
        jobs: list[JobPosting] = []
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        for region_name, region_config in enabled_regions.items():
            iso = region_config.get("country", "").upper()
            if iso not in _EU_EEA_CODES:
                continue

            for title in title_filters:
                page = 0
                while True:
                    payload = {
                        "dataSetRequest": {
                            "keywords": title,
                            "countryCode": iso,
                            "pageNumber": page,
                            "pageSize": _PAGE_SIZE,
                            "sortBy": "BEST_MATCH",
                        }
                    }
                    try:
                        resp = requests.post(
                            _API_URL,
                            json=payload,
                            headers=headers,
                            timeout=timeout,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as exc:
                        logger.warning(
                            "[eures] failed for %r in %s page %d: %s",
                            title,
                            region_name,
                            page,
                            exc,
                        )
                        break

                    vacancies = data.get("jvs") or []
                    if not vacancies:
                        break

                    before = len(jobs)
                    for item in vacancies:
                        header = item.get("header") or {}
                        job_title = str(header.get("title") or "")
                        if not title_matches(job_title, title_filters, _excluded):
                            continue

                        employer = str(header.get("employerName") or "")
                        place = str((header.get("placeOfWork") or {}).get("city") or "")
                        country_label = str((header.get("placeOfWork") or {}).get("countryCode") or iso)
                        location = ", ".join(filter(None, [place, country_label]))
                        posted = str(header.get("startDate") or "")[:10]

                        description_obj = item.get("jvDescription") or {}
                        description = strip_html(str(description_obj.get("description") or ""))

                        urls_obj = item.get("urls") or {}
                        job_url = str(urls_obj.get("applied") or urls_obj.get("detail") or "")
                        if not job_url:
                            jv_id = str(header.get("id") or "")
                            if jv_id:
                                job_url = f"https://eures.europa.eu/en/jobs-and-cts/jv/{jv_id}"

                        jobs.append(
                            JobPosting(
                                title=job_title,
                                company=employer,
                                url=job_url,
                                posted=posted,
                                location=location,
                                snippet=description[:3000],
                                source="EURES",
                                query=f"{title} @ {region_name}",
                                region=region_name,
                            )
                        )
                    logger.info(
                        "[eures] +%d jobs for %r in %s page %d",
                        len(jobs) - before,
                        title,
                        region_name,
                        page,
                    )

                    if len(vacancies) < _PAGE_SIZE:
                        break
                    page += 1

        logger.info("[eures] Complete: %d total jobs", len(jobs))
        return jobs
