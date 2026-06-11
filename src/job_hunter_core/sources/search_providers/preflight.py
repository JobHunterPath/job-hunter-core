"""Pre-flight health checks for search providers."""

from __future__ import annotations

import logging

from job_hunter_core.sources.search_providers.providers import (
    BraveProvider,
    ExaProvider,
    SearxngProvider,
    TavilyProvider,
)

logger = logging.getLogger(__name__)

# A query that any functioning web search API reliably answers.
_PROBE_QUERY = "software engineer"


def probe_search_providers() -> set[str]:
    """Test each configured search provider with a live probe query.

    Returns the set of provider names that are unreachable, rate-limited, or
    returning no results.  Call once at pipeline start, pass the result to
    set_run_disabled() so every SearchRouter instance created during the run
    automatically skips dead providers.  No state is read from or written to
    any file — the probe result is runtime-only.
    """
    disabled: set[str] = set()

    for provider in (SearxngProvider(), BraveProvider(), TavilyProvider(), ExaProvider()):
        if not provider.enabled():
            continue
        try:
            results = provider.search(_PROBE_QUERY, {}, count=1)
            if results:
                logger.info("[preflight] %s: OK", provider.name)
            else:
                logger.warning(
                    "[preflight] %s: probe returned 0 results — disabling for this run",
                    provider.name,
                )
                disabled.add(provider.name.lower())
        except Exception as exc:
            logger.warning(
                "[preflight] %s: probe failed (%s) — disabling for this run",
                provider.name,
                exc,
            )
            disabled.add(provider.name.lower())

    if disabled:
        logger.info("[preflight] providers disabled for this run: %s", sorted(disabled))
    return disabled
