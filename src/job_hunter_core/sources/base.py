from __future__ import annotations
import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from job_hunter_core.models import JobPosting


class JobSourceAdapter(abc.ABC):
    """Contract for a single job source returning filtered postings."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Stable identifier used in stats, logging, and config keys."""

    @abc.abstractmethod
    def fetch(
        self,
        title_filters: list[str],
        location_filter: str,
        config: dict,
        *,
        excluded_title_terms: list[str] | None = None,
    ) -> "list[JobPosting]":
        """Return matching postings. Must not raise — return [] on failure."""

    def is_enabled(self, config: dict) -> bool:  # noqa: ARG002
        return True
