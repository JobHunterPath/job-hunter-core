"""Search configuration and company loading utilities for the scraper."""

from __future__ import annotations

import logging
import os

import yaml

from job_hunter_core.core.config import ROOT as REPO_ROOT

ROOT = str(REPO_ROOT)
logger = logging.getLogger(__name__)


def load_search_config() -> dict:
    config_file = os.path.join(ROOT, "config", "search_config.yml")
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info("[scraper] Loaded search configuration from %s", config_file)
    return config


def load_companies(region: str | None = None) -> list[dict]:
    """Load enabled companies from search_config.yml, optionally scoped by region."""
    config = load_search_config()
    excluded = {name.lower() for name in config.get("excluded_companies", [])}
    companies = []

    regions_to_load = [region] if region else config.get("regions", {}).keys()

    for reg in regions_to_load:
        if reg not in config.get("regions", {}):
            logger.warning("[scraper] Region %r not found in search_config.yml", reg)
            continue

        region_config = config["regions"][reg]
        if not region_config.get("enabled", True):
            logger.info("[scraper] Region %r is disabled. Skipping.", reg)
            continue

        location = region_config.get("location", "")
        loaded = 0
        for company in region_config.get("companies", []):
            if company["name"].lower() in excluded:
                logger.info("[scraper] Skipping excluded company: %s", company["name"])
                continue
            companies.append(
                {
                    **company,
                    "region": reg,
                    "location": location,
                    "country": region_config.get("country", ""),
                    "search_lang": region_config.get("search_lang", ""),
                    "_region_config": region_config,
                }
            )
            loaded += 1

        logger.info(
            "[scraper] Loaded %s companies from region %r (location=%r)",
            loaded,
            reg,
            location,
        )

    logger.info("[scraper] Total: %s companies", len(companies))
    return companies


def build_queries(companies: list[dict], config: dict) -> list[tuple[str, str, str]]:
    """Build search queries. Returns (query, company_name, location)."""
    queries = []
    job_titles = config.get("global_search", {}).get("job_titles", [])
    excluded_title_terms = config.get("exclusion_rules", {}).get("excluded_title_terms", [])
    exclusions = " ".join(f'-"{term}"' for term in excluded_title_terms)

    if not job_titles:
        logger.warning("[scraper] global_search.job_titles is empty; no search queries built")
        return queries

    for company in companies:
        url = company["career_url"]
        name = company["name"]
        location = company.get("location", "")

        for title in job_titles:
            query = f'"{title}" site:{url}'
            if location:
                query += f' "{location}"'
            if exclusions:
                query += f" {exclusions}"
            queries.append((query, name, location or "global"))

    logger.info("[scraper] Built %s search queries for %s companies", len(queries), len(companies))
    return queries
