"""Search and career-page provider strategies.

The scraper and discovery jobs need the same fallback chain: cheap direct
fetching first, API search providers last.  Each provider implements the same
small interface so callers can use a Chain of Responsibility style router
without knowing provider-specific response shapes.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from html import unescape
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from core.config import (
    BRAVE_API_KEY,
    EXA_API_KEY,
    TAVILY_API_KEY,
    get_timeout,
    load_api_config,
)
from core.utils import title_matches

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
TAVILY_URL = "https://api.tavily.com/search"
EXA_URL = "https://api.exa.ai/search"

# Brave's web-search country enum is narrower than ISO 3166-1.  Keep unsupported
# countries in the query text via region.location, but do not send them as a
# param because Brave rejects them before fallback providers can help.
BRAVE_SUPPORTED_COUNTRIES = {
    "AR", "AU", "AT", "BE", "BR", "CA", "CL", "DK", "FI", "FR", "DE", "HK",
    "IN", "ID", "IT", "JP", "KR", "MY", "MX", "NL", "NZ", "NO", "PL", "PT",
    "PH", "RU", "SA", "ZA", "ES", "SE", "CH", "TW", "TR", "GB", "US",
}

JOB_HINTS = (
    "job", "jobs", "career", "careers", "position", "positions", "opening",
    "openings", "vacancy", "vacancies",
)

TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "gbraid", "wbraid", "mc_cid", "mc_eid", "igshid",
}
TRACKING_QUERY_PREFIXES = ("utm_",)
_PROVIDER_FAILURES: dict[str, int] = {}
_PROVIDER_FAILURES_LOCK = threading.Lock()


@dataclass
class SearchResult:
    url: str
    title: str
    description: str
    source: str


class SearchProvider:
    """Strategy interface for web-search providers."""

    name = "provider"

    def enabled(self) -> bool:
        return True

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        raise NotImplementedError


def _timeout(section: str) -> int:
    return get_timeout(section)


def _search_cfg() -> dict:
    return load_api_config().get("http", {}).get("search_providers", {}) or {}


def _with_scheme(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def canonicalize_url(url: str) -> str:
    """Normalize URLs for dedupe while preserving meaningful path/query data."""
    if not url:
        return ""
    parsed = urlparse(_with_scheme(url.strip()))
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower in TRACKING_QUERY_KEYS:
            continue
        if any(key_lower.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def _text(value: object) -> str:
    return unescape(str(value or "")).strip()


def _looks_like_job_url(url: str) -> bool:
    lower = url.lower()
    return any(hint in lower for hint in JOB_HINTS)


def _location_match(text: str, location: str) -> bool:
    if not location:
        return True
    lower = text.lower()
    location = location.lower()
    if location in lower:
        return True
    if "remote" in location and "remote" in lower:
        return True
    return False


def normalize_web_results(raw: list[dict], source: str) -> list[SearchResult]:
    results = []
    for item in raw:
        url = item.get("url") or item.get("link")
        if not url:
            continue
        results.append(
            SearchResult(
                url=url,
                title=_text(item.get("title") or item.get("name")),
                description=_text(
                    item.get("description")
                    or item.get("snippet")
                    or item.get("content")
                    or item.get("text")
                ),
                source=source,
            )
        )
    return results


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


class SearxngProvider(SearchProvider):
    name = "searxng"

    def __init__(self) -> None:
        self.base_url = (
            os.environ.get("SEARXNG_BASE_URL")
            or _search_cfg().get("searxng_base_url")
            or ""
        ).rstrip("/")

    def enabled(self) -> bool:
        return bool(self.base_url)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "safesearch": 0,
        }
        if region_config.get("search_lang"):
            params["language"] = region_config["search_lang"]
        resp = requests.get(
            f"{self.base_url}/search",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        raw = resp.json().get("results", [])[:count]
        return normalize_web_results(raw, "SearXNG")


class BraveProvider(SearchProvider):
    name = "brave"

    def enabled(self) -> bool:
        return bool(BRAVE_API_KEY)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        params = {
            "q": query,
            "count": count,
            "text_decorations": False,
            "spellcheck": False,
        }
        if region_config.get("search_lang"):
            params["search_lang"] = region_config["search_lang"]
        country = str(region_config.get("country") or "").upper()
        if country in BRAVE_SUPPORTED_COUNTRIES:
            params["country"] = country
        resp = requests.get(
            BRAVE_URL,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            params=params,
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        return normalize_web_results(resp.json().get("web", {}).get("results", []), "Brave")


class TavilyProvider(SearchProvider):
    name = "tavily"

    def enabled(self) -> bool:
        return bool(TAVILY_API_KEY)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": count,
            "include_answer": False,
            "include_raw_content": False,
        }
        resp = requests.post(TAVILY_URL, json=payload, timeout=_timeout("search_providers"))
        resp.raise_for_status()
        return normalize_web_results(resp.json().get("results", []), "Tavily")


class ExaProvider(SearchProvider):
    name = "exa"

    def enabled(self) -> bool:
        return bool(EXA_API_KEY)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        payload = {
            "query": query,
            "numResults": count,
            "type": "keyword",
            "contents": {"text": {"maxCharacters": 500}},
        }
        resp = requests.post(
            EXA_URL,
            json=payload,
            headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        raw = []
        for item in resp.json().get("results", []):
            raw.append({
                "url": item.get("url"),
                "title": item.get("title"),
                "description": item.get("text") or item.get("highlights"),
            })
        return normalize_web_results(raw, "Exa")


class SearchRouter:
    """Tries enabled search providers in configured order."""

    def __init__(self, providers: Optional[list[SearchProvider]] = None) -> None:
        self.providers = providers if providers is not None else _providers_from_order(_provider_order())
        self.max_consecutive_failures = int(
            _search_cfg().get("max_consecutive_failures", 3)
        )

    def _is_suppressed(self, provider: SearchProvider) -> bool:
        if self.max_consecutive_failures <= 0:
            return False
        failures = _provider_failure_count(provider.name)
        if failures < self.max_consecutive_failures:
            return False
        logger.warning(
            "[search] %s skipped after %s consecutive failure(s)",
            provider.name,
            failures,
        )
        return True

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        all_results: list[SearchResult] = []
        for provider in self.providers:
            if not provider.enabled():
                logger.debug("[search] %s disabled or missing credentials", provider.name)
                continue
            if self._is_suppressed(provider):
                continue
            try:
                logger.info("[search] %s: %s", provider.name, query[:80])
                results = provider.search(query, region_config, count=count)
                _reset_provider_failure(provider.name)
                if results:
                    all_results.extend(results)
                    break
            except Exception as exc:
                failures = _record_provider_failure(provider.name)
                logger.warning(
                    "[search] %s failed (%s/%s): %s",
                    provider.name,
                    failures,
                    self.max_consecutive_failures,
                    exc,
                )
        return all_results[:count]


class ProviderSearchRouter(SearchRouter):
    """Search router constrained to a caller-provided provider name order."""

    def __init__(self, provider_names: list[str]) -> None:
        super().__init__(_providers_from_order(provider_names))


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


def search_web(query: str, region_config: dict, count: int = 10) -> list[dict]:
    """Compatibility helper returning Brave-like dictionaries."""
    return [
        {
            "url": result.url,
            "title": result.title,
            "description": result.description,
            "source": result.source,
        }
        for result in SearchRouter().search(query, region_config, count=count)
    ]


_ATS_DISCOVERY_SITES = {
    "greenhouse": (
        "site:boards.greenhouse.io OR site:job-boards.greenhouse.io",
        r"(?:boards|job-boards)\.greenhouse\.io$",
        r"/jobs/\d+",
    ),
    "lever": (
        "site:jobs.lever.co",
        r"^jobs\.lever\.co$",
        r"^/[^/]+/[0-9a-f-]{36}",
    ),
    "ashby": (
        "site:jobs.ashbyhq.com",
        r"^jobs\.ashbyhq\.com$",
        r"^/[^/]+/[0-9a-f-]{36}",
    ),
    "smartrecruiters": (
        "site:jobs.smartrecruiters.com",
        r"^jobs\.smartrecruiters\.com$",
        r"^/[^/]+/\d+",
    ),
    "workable": (
        "site:apply.workable.com",
        r"^apply\.workable\.com$",
        r"^/[^/]+/j/[A-F0-9]+",
    ),
    "personio": (
        "site:jobs.personio.de OR site:jobs.personio.com",
        r"(?:jobs\.personio\.(?:de|com)|\.jobs\.personio\.de)$",
        r"/job/",
    ),
    "recruitee": (
        "site:recruitee.com",
        r"recruitee\.com$",
        r"/o/",
    ),
    "hibob": (
        "site:careers.hibob.com/jobs",
        r"\.careers\.hibob\.com$",
        r"/jobs/[0-9a-f-]{36}",
    ),
}


def _passes_ats_discovery_shape(url: str, source: str) -> bool:
    _, host_pattern, path_pattern = _ATS_DISCOVERY_SITES[source]
    parsed = urlparse(url)
    return (
        re.search(host_pattern, parsed.netloc, re.IGNORECASE) is not None
        and re.search(path_pattern, parsed.path, re.IGNORECASE) is not None
    )


def _company_from_ats_url(url: str, source: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if source in {"greenhouse", "lever", "ashby", "smartrecruiters", "workable"} and parts:
        return parts[0].replace("-", " ").replace("_", " ").strip().title()
    if source == "personio":
        if parsed.netloc.endswith(".jobs.personio.de"):
            return parsed.netloc.split(".jobs.personio.de", 1)[0].replace("-", " ").title()
        if parts and parts[0] != "job":
            return parts[0].replace("-", " ").title()
    if source == "recruitee":
        return parsed.netloc.split(".recruitee.com", 1)[0].replace("-", " ").title()
    if source == "hibob":
        return parsed.netloc.split(".careers.hibob.com", 1)[0].replace("-", " ").title()
    return ""


def discover_ats_jobs_by_search(
    title_filters: list[str],
    regions: dict[str, dict],
    excluded_title_terms: list[str] | None = None,
    *,
    provider_order: list[str] | None = None,
) -> list[dict]:
    """Find individual ATS job URLs from broad title+region search queries."""
    if not title_filters or not regions:
        return []

    cfg = _search_cfg().get("ats_discovery", {}) or {}
    if not cfg.get("enabled", True):
        return []

    max_results_per_query = int(cfg.get("results_per_query", 10))
    max_queries_per_region = int(cfg.get("max_queries_per_region", 0) or 0)
    max_total_queries = int(cfg.get("max_total_queries", 0) or 0)
    sources = cfg.get("sources") or list(_ATS_DISCOVERY_SITES)
    router = ProviderSearchRouter(provider_order or _provider_order())
    jobs: list[dict] = []
    seen: set[str] = set()
    total_queries = 0

    for region_name, region_config in regions.items():
        region_queries = 0
        location = region_config.get("location") or region_name
        for title in title_filters:
            for source in sources:
                if source not in _ATS_DISCOVERY_SITES:
                    continue
                if max_queries_per_region > 0 and region_queries >= max_queries_per_region:
                    logger.info("[search-discovery] query cap reached for region=%s", region_name)
                    break
                if max_total_queries > 0 and total_queries >= max_total_queries:
                    logger.info("[search-discovery] total query cap reached")
                    logger.info("[search-discovery] complete: %s jobs found", len(jobs))
                    return jobs
                site_query, _, _ = _ATS_DISCOVERY_SITES[source]
                query = f'({site_query}) "{title}" "{location}"'
                region_queries += 1
                total_queries += 1
                for result in router.search(query, region_config, count=max_results_per_query):
                    if not _passes_ats_discovery_shape(result.url, source):
                        continue
                    if not title_matches(result.title, title_filters, excluded_title_terms):
                        continue
                    canonical = canonicalize_url(result.url)
                    if canonical in seen:
                        continue
                    seen.add(canonical)
                    jobs.append({
                        "title": result.title,
                        "company": _company_from_ats_url(result.url, source),
                        "location": location,
                        "url": result.url,
                        "posted": "",
                        "snippet": result.description,
                        "source": f"{result.source} ATS discovery: {source}",
                        "query": query,
                    })

    logger.info("[search-discovery] complete: %s jobs found", len(jobs))
    return jobs


def extract_jobs_from_html(
    html: str,
    base_url: str,
    company_name: str,
    title_filters: list[str],
    location: str,
    source: str,
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href"))
        url = urljoin(base_url, href)
        text = " ".join(anchor.get_text(" ", strip=True).split())
        context = " ".join(
            anchor.parent.get_text(" ", strip=True).split()
            if anchor.parent else text
        )
        haystack = f"{text} {href} {context}"

        title_text = text or next((t for t in title_filters if t.lower() in haystack.lower()), "")

        if not _looks_like_job_url(url) and not title_matches(title_text or haystack, title_filters, excluded_title_terms):
            continue
        if not title_matches(title_text or haystack, title_filters, excluded_title_terms):
            continue
        if not _location_match(haystack, location):
            continue
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue

        seen.add(canonical)
        jobs.append({
            "title": text or next((t for t in title_filters if t.lower() in haystack.lower()), "Job"),
            "company": company_name,
            "url": url,
            "posted": "",
            "snippet": context or text,
            "source": source,
        })

    return jobs


def fetch_static_career_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    url = _with_scheme(company["career_url"])
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=_timeout("ats_scraper"),
        allow_redirects=True,
    )
    resp.raise_for_status()
    if not isinstance(resp.text, str):
        return []
    return extract_jobs_from_html(
        resp.text,
        resp.url or url,
        company["name"],
        title_filters,
        company.get("location", ""),
        "HTTP career page",
        excluded_title_terms,
    )


def fetch_playwright_career_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[search] playwright not installed; skipping career render")
        return []

    url = _with_scheme(company["career_url"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            pw_timeout = int(get_timeout("playwright") * 1000)
            page.goto(url, wait_until="networkidle", timeout=pw_timeout)
            html = page.content()
            return extract_jobs_from_html(
                html,
                page.url or url,
                company["name"],
                title_filters,
                company.get("location", ""),
                "Playwright career page",
                excluded_title_terms,
            )
        finally:
            browser.close()


def discover_company_homepage(company_name: str, region_config: dict) -> Optional[str]:
    location = region_config.get("location", "")
    query = f'"{company_name}" "{location}" official website careers'
    results = SearchRouter().search(query, region_config, count=5)
    for result in results:
        parsed = urlparse(result.url)
        if parsed.netloc and "linkedin." not in parsed.netloc and "glassdoor." not in parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


def search_career_urls(company_name: str, region_config: dict, count: int = 7) -> list[dict]:
    location = region_config.get("location", "")
    job_titles = region_config.get("job_titles", [])
    title_query = " OR ".join(f'"{title}"' for title in job_titles)
    ats_sites = (
        "site:boards.greenhouse.io OR site:job-boards.greenhouse.io "
        "OR site:jobs.lever.co OR site:jobs.smartrecruiters.com "
        "OR site:apply.workable.com OR site:jobs.ashbyhq.com "
        "OR site:careers.hibob.com OR site:recruitee.com "
        "OR site:jobs.personio.de OR site:jobs.personio.com"
    )
    queries = [f'"{company_name}" {location} {ats_sites}']
    if title_query:
        queries.append(f'"{company_name}" {location} {title_query} careers jobs')
    out: list[dict] = []
    seen = set()
    for query in queries:
        for item in search_web(query, region_config, count=count):
            canonical = canonicalize_url(item["url"])
            if canonical in seen:
                continue
            seen.add(canonical)
            out.append(item)
    return out
