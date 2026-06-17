"""Filtering and dedupe policy for discovered job postings."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from job_hunter_core.core.utils import title_matches
from job_hunter_core.sources.search_providers import canonicalize_url

logger = logging.getLogger(__name__)

_LISTING_ONLY_PATHS = {
    "/jobs",
    "/careers",
    "/positions",
    "/openings",
    "/vacancies",
    "/work-with-us",
    "/join-us",
}

_GERMAN_WORD_RE = re.compile(r"[a-z\u00e4\u00f6\u00fc\u00df]+", re.IGNORECASE)
_GERMAN_MIN_WORDS = 18
_GERMAN_MIN_HITS = 6
_GERMAN_MIN_UNIQUE_HITS = 4
_GERMAN_LANGUAGE_MARKERS = {
    "als",
    "auf",
    "aus",
    "bei",
    "das",
    "dein",
    "deine",
    "deinem",
    "deinen",
    "deiner",
    "dem",
    "den",
    "der",
    "des",
    "dich",
    "die",
    "du",
    "ein",
    "eine",
    "einem",
    "einen",
    "einer",
    "f\u00fcr",
    "fuer",
    "ihre",
    "ihren",
    "ihr",
    "im",
    "ist",
    "mit",
    "nicht",
    "oder",
    "sich",
    "sind",
    "sowie",
    "und",
    "uns",
    "unser",
    "unsere",
    "von",
    "wir",
    "zu",
    "zum",
    "zur",
}


def _looks_like_german_text(text: str) -> bool:
    words = _GERMAN_WORD_RE.findall(text.lower())
    if len(words) < _GERMAN_MIN_WORDS:
        return False

    hits = [word for word in words if word in _GERMAN_LANGUAGE_MARKERS]
    return len(hits) >= _GERMAN_MIN_HITS and len(set(hits)) >= _GERMAN_MIN_UNIQUE_HITS


_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(gmbh|ag|inc|inc\.|ltd|ltd\.|llc|plc|se|sa|s\.a\.|corp|corp\.|corporation|group)\b",
    re.IGNORECASE,
)


def normalize_company_name(company: str) -> str:
    normalized = _CORPORATE_SUFFIX_RE.sub("", company or "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower())
    return " ".join(normalized.split())


@dataclass(frozen=True)
class JobPolicy:
    config: dict

    @property
    def exclusion_rules(self) -> dict:
        return self.config.get("exclusion_rules", {})

    def is_valid_job_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        if not path:
            return False
        if path in _LISTING_ONLY_PATHS:
            return False

        segments = [s for s in path.split("/") if s]
        return len(segments) >= 2

    def is_excluded_url(self, url: str) -> bool:
        patterns = self.exclusion_rules.get("excluded_url_patterns", [])
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns)

    def is_stale_posting(self, title: str, snippet: str) -> bool:
        combined = (title + " " + snippet).lower()
        stale_indicators = self.exclusion_rules.get("stale_indicators", [])
        return any(indicator in combined for indicator in stale_indicators)

    def is_too_senior(self, title: str, snippet: str) -> bool:
        combined = (title + " " + snippet).lower()
        senior_flags = self.exclusion_rules.get("senior_flags", [])
        return any(flag in combined for flag in senior_flags)

    def is_excluded_company(self, company: str) -> bool:
        excluded = self.config.get("excluded_companies", [])
        company_norm = normalize_company_name(company)
        return bool(company_norm) and any(
            normalize_company_name(str(e)) == company_norm for e in excluded
        )

    def is_excluded_industry(self, snippet: str) -> bool:
        excluded_industries = self.exclusion_rules.get("excluded_industries", [])
        return any(kw in snippet.lower() for kw in excluded_industries)

    def is_german(self, title: str, snippet: str) -> bool:
        return self.is_excluded_language(title, snippet, language="german")

    def is_excluded_language(
        self, title: str, snippet: str, *, language: str | None = None
    ) -> bool:
        excluded_languages = [
            str(lang).strip().lower()
            for lang in self.exclusion_rules.get("excluded_languages", []) or []
            if str(lang).strip()
        ]
        if language:
            if language.lower() not in excluded_languages:
                return False
            languages = [language.lower()]
        else:
            languages = excluded_languages
        if not languages:
            return False

        language_indicators = self.exclusion_rules.get("language_indicators", {}) or {}
        combined = (title + " " + snippet).lower()
        for lang in languages:
            indicators = [
                str(value).strip().lower()
                for value in language_indicators.get(lang, []) or []
                if str(value).strip()
            ]
            if indicators and any(indicator in combined for indicator in indicators):
                return True
            if lang == "german" and _looks_like_german_text(combined):
                return True
        return False

    def accepts_job_content(self, job: dict, title_filters: list[str]) -> bool:
        title = job.get("title", "")
        company = job.get("company", "")
        snippet = job.get("snippet", "")
        excluded_title_terms = self.exclusion_rules.get("excluded_title_terms", [])

        if title_filters and not title_matches(title, title_filters, excluded_title_terms):
            logger.info("[skip] Title not in filters: %s", title[:60])
            return False
        if self.is_excluded_company(company):
            logger.info("[skip] Excluded company: %s", company[:60])
            return False
        if self.is_stale_posting(title, snippet):
            logger.info("[skip] Stale/closed posting: %s", title[:60])
            return False
        if self.is_excluded_language(title, snippet):
            logger.info("[skip] Excluded-language posting: %s", title[:60])
            return False
        if self.is_too_senior(title, snippet):
            logger.info("[skip] Too senior: %s", title[:60])
            return False
        if self.is_excluded_industry(snippet):
            logger.info("[skip] Excluded industry: %s", title[:60])
            return False
        return True

    def accepts_search_result_url(self, url: str, title: str, snippet: str) -> bool:
        if self.is_excluded_url(url):
            logger.info("[skip] Excluded URL pattern: %s", url[:80])
            return False
        if not self.is_valid_job_url(url):
            logger.info("[skip] Not a job posting URL: %s", url[:80])
            return False
        if self.is_stale_posting(title, snippet):
            logger.info("[skip] Stale/closed posting: %s", title[:60])
            return False
        return True


@dataclass
class JobAccumulator:
    config: dict
    seen_urls: set[str]
    results: list[dict]
    title_filters: list[str]
    lock: threading.Lock = field(default_factory=threading.Lock)
    cached_candidate_urls: set[str] = field(default_factory=set)
    candidate_cache_updates: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.policy = JobPolicy(self.config)

    def add_job(
        self,
        job: dict,
        allow_excluded_urls: bool = False,
        cache_candidate: bool = False,
    ) -> bool:
        url = job.get("url", "")
        if not url:
            return False

        canonical_url = canonicalize_url(url)
        if cache_candidate and self._is_cached_candidate(canonical_url, url):
            return False

        if not allow_excluded_urls and self.policy.is_excluded_url(url):
            logger.info("[skip] Excluded URL pattern: %s", url[:80])
            return False
        if not self.policy.accepts_job_content(job, self.title_filters):
            return False

        with self.lock:
            if canonical_url in self.seen_urls:
                return False
            self.seen_urls.add(canonical_url)
            self.results.append(job)

        logger.info(
            "[found] %s @ %s [%s]",
            job.get("title", "")[:50],
            job.get("company", "?"),
            job.get("source", "?"),
        )
        return True

    def _is_cached_candidate(self, canonical_url: str, url: str) -> bool:
        with self.lock:
            if canonical_url in self.cached_candidate_urls:
                logger.info("[skip] Cached discovery candidate: %s", url[:80])
                return True
            self.candidate_cache_updates.add(canonical_url)
        return False


def make_job_filter(
    config: dict,
    seen_urls: set[str],
    results: list[dict],
    title_filters: list[str],
    lock: threading.Lock | None = None,
    cached_candidate_urls: set[str] | None = None,
    candidate_cache_updates: set[str] | None = None,
) -> Any:
    accumulator = JobAccumulator(
        config=config,
        seen_urls=seen_urls,
        results=results,
        title_filters=title_filters,
        lock=lock or threading.Lock(),
        cached_candidate_urls=cached_candidate_urls if cached_candidate_urls is not None else set(),
        candidate_cache_updates=(
            candidate_cache_updates if candidate_cache_updates is not None else set()
        ),
    )
    return accumulator.add_job
