"""SearchRouter, search_web, provider registry, and all mutable module-level state."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from job_hunter_core.core.api_budget import (
    _budget_cfg,
    _is_exhausted,
    _read_state,
    _state_path,
    is_api_quota_exhausted,
    mark_api_exhausted,
)
from job_hunter_core.sources.search_providers.providers import (
    BraveProvider,
    ExaProvider,
    SearchProvider,
    SearxngProvider,
    TavilyProvider,
    _search_cfg,
)

if TYPE_CHECKING:
    from job_hunter_core.sources.search_providers._result import SearchResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mutable module-level state — all lives here
# ---------------------------------------------------------------------------
_PROVIDER_FAILURES: dict[str, int] = {}
_PROVIDER_FAILURES_LOCK = threading.Lock()

_SEARXNG_ZERO_THRESHOLD: int = 5
_searxng_consecutive_zeros: int = 0
_SEARXNG_ZERO_LOCK = threading.Lock()
_ats_only_logged: bool = False


def _provider_failure_count(name: str) -> int:
    with _PROVIDER_FAILURES_LOCK:
        return _PROVIDER_FAILURES.get(name, 0)


def _reset_provider_failure(name: str) -> None:
    with _PROVIDER_FAILURES_LOCK:
        _PROVIDER_FAILURES[name] = 0


def _record_provider_failure(name: str) -> int:
    with _PROVIDER_FAILURES_LOCK:
        failures = _PROVIDER_FAILURES.get(name, 0) + 1
        _PROVIDER_FAILURES[name] = failures
        return failures


def _provider_registry() -> dict[str, SearchProvider]:
    return {
        "searxng": SearxngProvider(),
        "brave": BraveProvider(),
        "tavily": TavilyProvider(),
        "exa": ExaProvider(),
    }


def _provider_order() -> list[str]:
    return list(_search_cfg().get("order") or _provider_registry())


def _providers_from_order(provider_names: list[str]) -> list[SearchProvider]:
    available = _provider_registry()
    return [available[name] for name in provider_names if name in available]


def all_providers_exhausted(api_cfg: dict | None = None) -> bool:
    """Return True when all search providers are effectively unavailable."""
    global _ats_only_logged

    cfg = _budget_cfg(api_cfg)
    state = _read_state(_state_path(cfg))
    brave_out = _is_exhausted("brave", state)
    tavily_out = _is_exhausted("tavily", state)
    exa_out = _is_exhausted("exa", state)
    paid_exhausted = brave_out and tavily_out and exa_out

    searxng_unavailable = not SearxngProvider().enabled()

    result = paid_exhausted and searxng_unavailable

    if result:
        with _SEARXNG_ZERO_LOCK:
            if not _ats_only_logged:
                logger.info("[search] all providers exhausted — switching to ATS-only mode")
                _ats_only_logged = True

    return result


class SearchRouter:
    """Tries enabled search providers in configured order."""

    def __init__(
        self,
        providers: list[SearchProvider] | None = None,
        *,
        disabled: set[str] | None = None,
        allowed: set[str] | None = None,
    ) -> None:
        self.providers = (
            providers if providers is not None else _providers_from_order(_provider_order())
        )
        self.max_consecutive_failures = int(_search_cfg().get("max_consecutive_failures", 3))
        self._disabled: set[str] = {p.lower() for p in (disabled or set())}
        self._allowed: set[str] | None = (
            {p.lower() for p in allowed} if allowed is not None else None
        )

    def _is_suppressed(self, provider: SearchProvider) -> bool:
        if self.max_consecutive_failures <= 0:
            return False
        failures = _provider_failure_count(provider.name)
        if failures < self.max_consecutive_failures:
            return False
        logger.warning(
            "[search] %s suppressed after %s consecutive transient failure(s); "
            "will resume after a successful call from another provider",
            provider.name,
            failures,
        )
        return True

    @staticmethod
    def _is_exhausted(provider: SearchProvider) -> bool:
        """Return True when the provider's monthly quota is already marked exhausted."""
        from job_hunter_core.core.api_budget import _budget_cfg, _read_state, _state_path

        cfg = _budget_cfg()
        if not cfg.get("enabled", True):
            return False
        state = _read_state(_state_path(cfg))
        exhausted = state.get("exhausted", {})
        return provider.name.lower() in exhausted

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        all_results: list[SearchResult] = []
        any_keyed_provider_tried = False

        for provider in self.providers:
            pname = provider.name.lower()
            if self._allowed is not None and pname not in self._allowed:
                logger.debug("[search] %s skipped: not in allowed set", provider.name)
                continue
            if pname in self._disabled:
                logger.debug("[search] %s skipped: pre-flight exhausted this run", provider.name)
                continue

            if not provider.enabled():
                logger.debug("[search] %s disabled or missing credentials", provider.name)
                continue

            if self._is_exhausted(provider):
                logger.info(
                    "[search] %s skipped: monthly quota already exhausted for this month",
                    provider.name,
                )
                continue

            if self._is_suppressed(provider):
                continue

            any_keyed_provider_tried = True
            try:
                logger.info("[search] %s: %s", provider.name, query[:80])
                results = provider.search(query, region_config, count=count)
                _reset_provider_failure(provider.name)
                if results:
                    all_results.extend(results)
                    break
            except Exception as exc:
                if is_api_quota_exhausted(exc):
                    mark_api_exhausted(provider.name, exc=exc)
                    _reset_provider_failure(provider.name)
                    logger.warning(
                        "[search] %s quota exhausted; continuing to next provider",
                        provider.name,
                    )
                    continue
                failures = _record_provider_failure(provider.name)
                logger.warning(
                    "[search] %s transient failure (%s/%s): %s",
                    provider.name,
                    failures,
                    self.max_consecutive_failures,
                    exc,
                )

        if not any_keyed_provider_tried and not all_results:
            logger.debug(
                "[search] no enabled providers with credentials; returning empty result set"
            )

        return all_results[:count]


class ProviderSearchRouter(SearchRouter):
    """Search router constrained to a caller-provided provider name order."""

    def __init__(
        self,
        provider_names: list[str],
        *,
        disabled: set[str] | None = None,
        allowed: set[str] | None = None,
    ) -> None:
        super().__init__(_providers_from_order(provider_names), disabled=disabled, allowed=allowed)


def search_web(
    query: str,
    region_config: dict,
    count: int = 10,
    *,
    disabled: set[str] | None = None,
    allowed: set[str] | None = None,
) -> list[dict]:
    """Compatibility helper returning Brave-like dictionaries."""
    return [
        {
            "url": result.url,
            "title": result.title,
            "description": result.description,
            "source": result.source,
        }
        for result in SearchRouter(disabled=disabled, allowed=allowed).search(
            query, region_config, count=count
        )
    ]
