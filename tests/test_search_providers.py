"""Tests for generic search-provider routing behavior."""

from concurrent.futures import ThreadPoolExecutor

from job_hunter_core.sources import search_providers


class FailingProvider(search_providers.SearchProvider):
    name = "failing"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        raise RuntimeError("boom")


class EmptyProvider(search_providers.SearchProvider):
    name = "empty"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        return []


class StaticProvider(search_providers.SearchProvider):
    name = "static"

    def search(self, query: str, region_config: dict, count: int = 10):
        return [
            search_providers.SearchResult(
                url="https://jobs.smartrecruiters.com/TestCo/123456-product-manager",
                title="Product Manager",
                description="Dublin product role",
                source="SearXNG",
            ),
            search_providers.SearchResult(
                url="https://jobs.smartrecruiters.com/TestCo",
                title="Product Manager jobs",
                description="Listing page",
                source="SearXNG",
            ),
        ]


def test_router_skips_provider_after_configured_consecutive_failures():
    search_providers._PROVIDER_FAILURES.clear()
    failing = FailingProvider()
    fallback = EmptyProvider()
    router = search_providers.SearchRouter(providers=[failing, fallback])
    router.max_consecutive_failures = 3

    for _ in range(4):
        router.search("query", {}, count=1)

    assert failing.calls == 3
    assert fallback.calls == 4


def test_router_failure_counter_is_thread_safe():
    search_providers._PROVIDER_FAILURES.clear()
    router = search_providers.SearchRouter(providers=[FailingProvider()])
    router.max_consecutive_failures = 100

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: router.search("query", {}, count=1), range(20)))

    assert search_providers._PROVIDER_FAILURES["failing"] == 20


def test_canonicalize_url_strips_tracking_for_dedupe():
    left = "https://www.example.com/jobs/123/?utm_source=x&b=2&a=1#details"
    right = "https://example.com/jobs/123?a=1&b=2"

    assert search_providers.canonicalize_url(left) == search_providers.canonicalize_url(right)


def test_discover_ats_jobs_by_search_extracts_expanded_ats_shapes(monkeypatch):
    class FakeRouter:
        def __init__(self, provider_order):
            self.provider_order = provider_order

        def search(self, query: str, region_config: dict, count: int = 10):
            assert self.provider_order == ["searxng", "brave"]
            return StaticProvider().search(query, region_config, count=count)

    monkeypatch.setattr(search_providers, "ProviderSearchRouter", FakeRouter)
    monkeypatch.setattr(
        search_providers,
        "_search_cfg",
        lambda: {
            "ats_discovery": {
                "enabled": True,
                "sources": ["smartrecruiters"],
                "results_per_query": 10,
            }
        },
    )

    jobs = search_providers.discover_ats_jobs_by_search(
        ["Product Manager"],
        {"dublin": {"location": "Dublin"}},
        provider_order=["searxng", "brave"],
    )

    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://jobs.smartrecruiters.com/TestCo/123456-product-manager"
    assert jobs[0]["company"] == "Testco"
    assert jobs[0]["source"] == "SearXNG ATS discovery: smartrecruiters"


def test_discover_ats_jobs_respects_query_caps(monkeypatch):
    queries = []

    class FakeRouter:
        def __init__(self, provider_order):
            self.provider_order = provider_order

        def search(self, query: str, region_config: dict, count: int = 10):
            queries.append(query)
            return []

    monkeypatch.setattr(search_providers, "ProviderSearchRouter", FakeRouter)
    monkeypatch.setattr(
        search_providers,
        "_search_cfg",
        lambda: {
            "ats_discovery": {
                "enabled": True,
                "sources": ["greenhouse", "lever", "ashby"],
                "results_per_query": 10,
                "max_queries_per_region": 2,
                "max_total_queries": 3,
            }
        },
    )

    jobs = search_providers.discover_ats_jobs_by_search(
        ["Product Manager", "Product Owner"],
        {
            "berlin": {"location": "Berlin"},
            "dublin": {"location": "Dublin"},
        },
    )

    assert jobs == []
    assert len(queries) == 3


def test_brave_provider_uses_shared_search_provider_timeout(monkeypatch):
    sections = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"web": {"results": []}}

    def fake_timeout(section: str) -> int:
        sections.append(section)
        return 7

    def fake_get(*args, **kwargs):
        assert kwargs["timeout"] == 7
        return FakeResponse()

    monkeypatch.setattr(search_providers, "_timeout", fake_timeout)
    monkeypatch.setattr(search_providers.requests, "get", fake_get)

    assert search_providers.BraveProvider().search("query", {}, count=1) == []
    assert sections == ["search_providers"]


# ── Task 2: Exhausted provider fallback ──────────────────────────────────────


class ExhaustedProvider(search_providers.SearchProvider):
    """Simulates a provider whose quota is exhausted (reserve_api_call returns False)."""

    name = "exhausted_provider"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        return []


class GoodProvider(search_providers.SearchProvider):
    """Provider that always returns one result."""

    name = "good_provider"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        return [
            search_providers.SearchResult(
                url="https://example.com/job/1",
                title="Product Manager",
                description="Great role",
                source="good_provider",
            )
        ]


def test_router_skips_exhausted_provider_and_continues_to_next(monkeypatch):
    """When a provider is pre-marked exhausted, the router skips it and tries the next one."""
    search_providers._PROVIDER_FAILURES.clear()

    exhausted = ExhaustedProvider()
    good = GoodProvider()

    # Mark exhausted_provider as quota-exhausted without a real state file
    monkeypatch.setattr(
        search_providers.SearchRouter,
        "_is_exhausted",
        lambda self, provider: provider.name == "exhausted_provider",
    )

    router = search_providers.SearchRouter(providers=[exhausted, good])
    results = router.search("query", {}, count=5)

    assert exhausted.calls == 0, "exhausted provider must not be called"
    assert good.calls == 1
    assert len(results) == 1


def test_router_quota_exhaustion_exception_does_not_suppress_next_provider(monkeypatch):
    """A quota-exhaustion exception resets the failure counter and continues to the next provider."""
    search_providers._PROVIDER_FAILURES.clear()

    class QuotaProvider(search_providers.SearchProvider):
        name = "quota_provider"
        calls = 0

        def search(self, query, region_config, count=10):
            self.calls += 1

            class FakeResp:
                status_code = 402
                reason = "Payment Required"
                text = "quota exceeded"

            exc = Exception("quota exceeded")
            exc.response = FakeResp()
            raise exc

    quota = QuotaProvider()
    good = GoodProvider()

    # Treat any exception from quota_provider as quota-exhausted

    monkeypatch.setattr(
        search_providers,
        "is_api_quota_exhausted",
        lambda exc: getattr(getattr(exc, "response", None), "status_code", None) == 402,
    )
    monkeypatch.setattr(search_providers, "mark_api_exhausted", lambda *a, **kw: None)
    monkeypatch.setattr(
        search_providers.SearchRouter,
        "_is_exhausted",
        lambda self, provider: False,  # not pre-exhausted; let the exception path trigger
    )

    router = search_providers.SearchRouter(providers=[quota, good])
    results = router.search("query", {}, count=5)

    assert quota.calls == 1
    assert good.calls == 1
    assert len(results) == 1
    # Failure counter for quota_provider must be 0 (reset after quota exc, not incremented)
    assert search_providers._PROVIDER_FAILURES.get("quota_provider", 0) == 0


def test_router_no_key_provider_skipped_silently():
    """A provider with no credentials is skipped at DEBUG level without noisy warnings."""
    search_providers._PROVIDER_FAILURES.clear()

    class NoKeyProvider(search_providers.SearchProvider):
        name = "no_key"
        calls = 0

        def enabled(self) -> bool:
            return False

        def search(self, query, region_config, count=10):
            self.calls += 1
            return []

    no_key = NoKeyProvider()
    good = GoodProvider()

    router = search_providers.SearchRouter(providers=[no_key, good])
    results = router.search("query", {}, count=5)

    assert no_key.calls == 0
    assert good.calls == 1
    assert len(results) == 1


# ── T-7: Search exhaustion detection ─────────────────────────────────────────


def _reset_exhaustion_state():
    """Reset module-level exhaustion counters to their defaults."""
    import job_hunter_core.sources.search_providers as sp

    with sp._SEARXNG_ZERO_LOCK:
        sp._searxng_consecutive_zeros = 0
        sp._ats_only_logged = False


def test_all_providers_exhausted_returns_false_with_budget(monkeypatch):
    """Returns False when no paid providers are exhausted."""
    _reset_exhaustion_state()

    # Patch _is_exhausted to always return False (none exhausted)
    monkeypatch.setattr(search_providers, "_is_exhausted", lambda provider, state: False)
    monkeypatch.setattr(search_providers, "_read_state", lambda path: {})
    monkeypatch.setattr(search_providers, "_budget_cfg", lambda api_cfg=None: {})
    monkeypatch.setattr(search_providers, "_state_path", lambda cfg: "dummy_path")

    result = search_providers.all_providers_exhausted()
    assert result is False

    _reset_exhaustion_state()


def test_all_providers_exhausted_returns_true_when_all_exhausted(monkeypatch):
    """Returns True when all paid providers exhausted and SearXNG unavailable."""
    _reset_exhaustion_state()

    monkeypatch.setattr(search_providers, "_is_exhausted", lambda provider, state: True)
    monkeypatch.setattr(search_providers, "_read_state", lambda path: {})
    monkeypatch.setattr(search_providers, "_budget_cfg", lambda api_cfg=None: {})
    monkeypatch.setattr(search_providers, "_state_path", lambda cfg: "dummy_path")
    # SearXNG not configured
    monkeypatch.setattr(search_providers.SearxngProvider, "enabled", lambda self: False)

    result = search_providers.all_providers_exhausted()
    assert result is True

    _reset_exhaustion_state()


def test_discover_ats_jobs_by_search_returns_empty_when_exhausted(monkeypatch, caplog):
    """discover_ats_jobs_by_search() returns [] and logs when all providers exhausted."""
    import logging

    _reset_exhaustion_state()

    monkeypatch.setattr(search_providers, "all_providers_exhausted", lambda api_cfg=None: True)
    monkeypatch.setattr(
        search_providers,
        "_search_cfg",
        lambda: {"ats_discovery": {"enabled": True}},
    )
    monkeypatch.setattr(search_providers, "load_api_config", lambda: {})

    with caplog.at_level(logging.INFO, logger=search_providers.logger.name):
        result = search_providers.discover_ats_jobs_by_search(
            ["Software Engineer"],
            {"EU": {"location": "Europe"}},
        )

    assert result == []
    assert any(
        "[search-discovery] skipped: all providers exhausted" in record.message
        for record in caplog.records
    )

    _reset_exhaustion_state()


def test_searxng_consecutive_zeros_increments(monkeypatch):
    """SearxngProvider.search() increments _searxng_consecutive_zeros on zero results."""
    import job_hunter_core.sources.search_providers as sp

    _reset_exhaustion_state()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    monkeypatch.setattr(search_providers.requests, "get", lambda *a, **kw: FakeResponse())

    provider = sp.SearxngProvider.__new__(sp.SearxngProvider)
    provider.base_url = "http://localhost:8888"

    for _ in range(3):
        provider.search("test query", {})

    with sp._SEARXNG_ZERO_LOCK:
        count = sp._searxng_consecutive_zeros
    assert count == 3

    _reset_exhaustion_state()
