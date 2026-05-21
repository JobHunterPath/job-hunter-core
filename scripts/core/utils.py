"""
Shared utility functions used across pipeline stages.
"""

from html import unescape
import re
import requests


def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace to plain text."""
    text = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</(script|style|noscript)>",
        " ",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def location_matches(location_str: str, target: str) -> bool:
    """Return True if target appears (case-insensitive) in location_str, or if target is empty."""
    if not target:
        return True
    return target.lower() in location_str.lower()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a phrase on word boundaries while allowing punctuation between words."""
    words = re.findall(r"[a-z0-9]+", phrase.lower())
    if not words:
        return False
    pattern = r"\b" + r"[\W_]+".join(re.escape(word) for word in words) + r"\b"
    return re.search(pattern, text.lower()) is not None


def title_matches(
    title: str,
    title_filters: list[str],
    excluded_terms: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """
    Return True only for configured product title phrases.

    The pipeline is intentionally strict here because every false positive can
    trigger URL checks, LLM calls, JD enrichment, LaTeX compilation, and cover
    letter generation. Empty title filters still mean "allow all" for callers
    that deliberately disable title filtering.
    """
    if not title_filters:
        return True

    if excluded_terms and any(_contains_phrase(title, term) for term in excluded_terms):
        return False

    return any(_contains_phrase(title, title_filter) for title_filter in title_filters)


def url_is_alive(url: str, timeout: int = 5) -> bool:
    """
    HEAD-check a URL. Returns False only on definitive 4xx/5xx responses.
    Returns True on network errors (a transient error does not mean the job is dead).
    """
    try:
        resp = requests.head(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 405:
            resp = requests.get(
                url, timeout=timeout, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
        return resp.status_code < 400
    except Exception:
        return True  # network error != dead posting
