"""Search configuration utilities for source-first scraping."""

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


def enabled_regions(config: dict, region: str | None = None) -> dict[str, dict]:
    """Return enabled search regions, optionally scoped to one region key."""
    regions = config.get("regions", {}) or {}

    if region:
        region_config = regions.get(region)
        if not region_config:
            logger.warning("[scraper] Region %r not found in search_config.yml", region)
            return {}
        if not region_config.get("enabled", True):
            logger.info("[scraper] Region %r is disabled. Skipping.", region)
            return {}
        return {region: region_config}

    return {
        name: region_config
        for name, region_config in regions.items()
        if isinstance(region_config, dict) and region_config.get("enabled", True)
    }
