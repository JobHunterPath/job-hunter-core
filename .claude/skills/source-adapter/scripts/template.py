"""Minimal JobSourceAdapter skeleton — copy to src/job_hunter_core/sources/<platform>_source.py."""
from __future__ import annotations

import logging

from job_hunter_core.models import JobPosting
from job_hunter_core.sources.base import JobSourceAdapter

logger = logging.getLogger(__name__)


class MyPlatformSource(JobSourceAdapter):
    @property
    def name(self) -> str:
        return "myplatform"

    def fetch(
        self,
        title_filters: list[str],
        enabled_regions: dict,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> list[JobPosting]:
        try:
            # TODO: implement fetch logic
            return []
        except Exception as exc:
            logger.debug("[myplatform] fetch failed: %s", exc)
            return []
