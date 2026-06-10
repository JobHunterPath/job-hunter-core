"""
Fetch and parse a job description from a raw URL or pasted text.

Extracts the job title, company name, and description text using a staged pipeline:
  1. HTTP GET the page and strip HTML to plain text.
  2. If the page is JS-rendered and yields too little text, fall back to Playwright
     to render the page in a real browser (optional dependency).
  3. An LLM parses the resulting text into structured fields.

Playwright is optional — install it only when needed:
  python -m pip install playwright && playwright install chromium
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

import requests

from job_hunter_core.core.llm_client import get_llm_client
from job_hunter_core.core.llm_utils import extract_json_object, get_llm_role_settings
from job_hunter_core.core.utils import strip_html

logger = logging.getLogger(__name__)

# Minimum body-text length before we consider the static extraction sufficient.
_MIN_TEXT_LENGTH = 300
_LLM_INPUT_MAX_CHARS = 8000    # page text chars passed to the LLM extraction prompt
_FALLBACK_DESC_MAX_CHARS = 4000  # fallback plain-text chars used when LLM extraction yields nothing

# Map ATS/career URL patterns → company name extractor
_ATS_PATTERNS = [
    (r"greenhouse\.io/([^/?#]+)", lambda m: m.group(1)),
    (r"lever\.co/([^/?#]+)", lambda m: m.group(1)),
    (r"jobs\.lever\.co/([^/?#]+)", lambda m: m.group(1)),
    # Use [^./]+ (exclude both dot and slash) so the subdomain label is matched,
    # not the entire scheme+host prefix (e.g. "https://myco" instead of "myco").
    (r"([^./]+)\.jobs\.personio\.de", lambda m: m.group(1)),
    (r"([^./]+)\.breezy\.hr", lambda m: m.group(1)),
    (r"([^./]+)\.workable\.com", lambda m: m.group(1)),
    (r"jobs\.smartrecruiters\.com/([^/?#]+)", lambda m: m.group(1)),
    (r"([^./]+)\.recruitee\.com", lambda m: m.group(1)),
    (r"careers\.([^./]+)\.", lambda m: m.group(1)),
    (r"jobs\.([^./]+)\.", lambda m: m.group(1)),
]

_EXTRACT_SYSTEM = (
    "You are a job posting parser. "
    "Return ONLY valid JSON with no markdown fences and no explanation."
)

_EXTRACT_PROMPT = """\
Extract the job details from this job posting page text.

URL: {url}

PAGE TEXT (first 8000 chars):
{text}

Return JSON:
{{
  "title": "exact job title from the posting",
  "company": "company name",
  "description": "the full job description text including responsibilities and requirements — at least 400 words if available"
}}

If a field cannot be found, use null."""


def _guess_company(url: str) -> str | None:
    """Guess company name from known ATS URL patterns."""
    for pattern, extractor in _ATS_PATTERNS:
        m = re.search(pattern, url, re.IGNORECASE)
        if m:
            raw = extractor(m)
            return raw.replace("-", " ").replace("_", " ").title()
    return None


def _fetch_html(url: str, timeout: int = 12) -> str | None:
    """GET the page and return raw HTML, or None on failure."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            },
        )
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.HTTPError as e:
        logger.error(f"[jd_fetcher] HTTP {e.response.status_code} for {url}")
    except Exception as e:
        logger.error(f"[jd_fetcher] Failed to fetch {url}: {e}")
    return None


def _fetch_playwright(url: str, timeout_ms: int = 20_000) -> str | None:
    """Render a JS-gated page with Playwright and return plain text.

    Uses Chromium in headless mode. Returns None if playwright is not
    installed or if rendering fails — callers should treat this as a
    best-effort enhancement, not a hard requirement.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("[jd_fetcher] playwright not installed; JS rendering unavailable")
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    )
                )
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
                return strip_html(html)
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"[jd_fetcher] Playwright failed for {url}: {e}")
    return None


def _llm_extract(text: str, url: str) -> dict[str, str]:
    """Use an LLM to extract title, company, and description from page text."""
    settings = get_llm_role_settings("jd_extraction")

    try:
        raw = get_llm_client("jd_extraction").complete(
            system=_EXTRACT_SYSTEM,
            user=_EXTRACT_PROMPT.format(text=text[:_LLM_INPUT_MAX_CHARS], url=url),
            model=settings.model,
            max_tokens=settings.max_tokens,
        )
        return json.loads(extract_json_object(raw))
    except Exception as e:
        logger.warning(f"[jd_fetcher] Extraction failed ({e}); falling back to raw text")
        return {}


def _normalize_extracted_job(extracted: Any) -> dict[str, str]:
    """Normalize LLM extraction output to one job dict.

    Some pages or models can produce a JSON array even though the prompt asks
    for a single object. Prefer the first object that looks like a job posting.
    """
    if isinstance(extracted, dict):
        return extracted

    if isinstance(extracted, list):
        for item in extracted:
            if isinstance(item, dict) and any(
                item.get(key) for key in ("title", "company", "description")
            ):
                return item

    logger.warning(
        "[jd_fetcher] Unexpected extraction shape %s; falling back to raw text",
        type(extracted).__name__,
    )
    return {}


def fetch_jd(url: str, use_llm: bool = True) -> dict | None:
    """
    Fetch and parse a job description from a URL.

    Pipeline:
      1. HTTP GET + HTML strip.
      2. If extracted text is too sparse (<300 chars), retry with Playwright
         for JS-rendered pages.
      3. LLM extracts title, company, and description from the best available text
         unless use_llm=False. Enrichment callers can skip the LLM when they
         only need the page text as a richer snippet.

    Returns a job dict compatible with the pipeline (keys: title, company,
    url, snippet, posted, source), or None if no usable description was found.
    """
    logger.info(f"[jd_fetcher] Fetching: {url}")

    html = _fetch_html(url)
    if not html:
        return None

    plain_text = strip_html(html)

    if len(plain_text) < _MIN_TEXT_LENGTH:
        logger.info(
            f"[jd_fetcher] Sparse content ({len(plain_text)} chars) from {url}; "
            "trying Playwright for JS rendering"
        )
        pw_text = _fetch_playwright(url)
        if pw_text and len(pw_text) > len(plain_text):
            plain_text = pw_text
            logger.info(f"[jd_fetcher] Playwright extracted {len(plain_text)} chars")

    extracted = _normalize_extracted_job(_llm_extract(plain_text, url)) if use_llm else {}

    title = extracted.get("title") or "Unknown Role"
    company = extracted.get("company") or _guess_company(url) or "Unknown Company"
    description = extracted.get("description") or plain_text[:_FALLBACK_DESC_MAX_CHARS]

    if not description.strip():
        logger.warning(f"[jd_fetcher] No description extracted from {url}")
        return None

    return {
        "title": title,
        "company": company,
        "url": url,
        "snippet": description,
        "posted": "",
        "source": "direct_link",
    }


def jd_from_text(
    text: str,
    *,
    title: str | None = None,
    company: str | None = None,
) -> dict | None:
    """
    Build a pipeline-compatible job dict from raw pasted job description text.

    Uses LLM extraction to infer title and company when not supplied.
    Returns None if the text is empty or yields no usable description.
    """
    if not text or not text.strip():
        return None

    if not title or not company:
        extracted = _normalize_extracted_job(_llm_extract(text, "raw_text"))
        title = title or extracted.get("title") or "Unknown Role"
        company = company or extracted.get("company") or "Unknown Company"
        description = extracted.get("description") or text[:_FALLBACK_DESC_MAX_CHARS]
    else:
        description = text[:_FALLBACK_DESC_MAX_CHARS]

    if not description.strip():
        return None

    uid = hashlib.sha1(text.encode()).hexdigest()[:12]
    return {
        "title": title,
        "company": company,
        "url": f"raw://{uid}",
        "snippet": description,
        "posted": "",
        "source": "raw_text",
    }
