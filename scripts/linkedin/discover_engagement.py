"""Discover LinkedIn people/posts and draft non-transactional networking text."""

from __future__ import annotations

import argparse
import os
import re
from datetime import date, timedelta
from pathlib import Path

from core.config import setup_logging
from linkedin.common import (
    append_section,
    complete_linkedin,
    configured_path,
    extract_json,
    format_yaml_list,
    load_linkedin_config,
    today_slug,
)
from sources.search_providers import search_web

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

SYSTEM = """You curate LinkedIn networking and engagement candidates.
Return JSON only. Do not include markdown fences."""

PROMPT = """Review these public LinkedIn search results and produce human-reviewed
engagement and networking suggestions. The user acts manually on everything.

POSITIONING (the user's professional context — use this when writing comments):
{positioning}

TARGET PEOPLE:
{target_people}

TOPICS:
{topics}

COMMENT RULES (for posts):
- Write a 1-2 sentence draft comment the user can post as-is or lightly edit
- Write from the user's positioning above — add a concrete perspective or
  observation, not just agreement or praise
- Reference something specific in the post excerpt: a claim, trade-off, data
  point, or framing that the user can react to from their own experience
- Do not open with "useful framing", "great post", "I agree", or generic openers
- Do not write a comment that could apply to any post on the same topic
- Max 40 words
- If the excerpt is too thin to write something specific, return an empty string

MESSAGE RULES (for people):
- No job ask, no referral ask, no generic flattery, no "pick your brain"
- Max {max_message_words} words per message
- Each variant must reference something specific about this person: their actual
  role, company, a product they built, or what they post about — not just the
  topic name

FORBIDDEN PHRASES:
{forbidden_phrases}

POSTS (with excerpts):
{posts}

PEOPLE:
{people}

Return a JSON object with keys "people" and "posts".
Each person: name, role_or_context, url, why_relevant, relationship_type,
suggested_action, message_variants (list of 2 strings, each specific to this person).
Each post: author_or_source, topic, url, why_relevant, suggested_comment
(ready-to-post 1-2 sentence draft from the user's POV, or empty string)."""


def _topic_from_query(query: str) -> str:
    match = re.search(r'"([^"]+)"', query or "")
    return match.group(1) if match else "this topic"


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+-\s+LinkedIn\s*$", "", title or "", flags=re.IGNORECASE)
    title = re.sub(r"\s+\|\s+LinkedIn\s*$", "", title, flags=re.IGNORECASE)
    return title.strip() or "LinkedIn result"


def _person_name(title: str) -> str:
    cleaned = _clean_title(title)
    for separator in (" - ", " | ", " @ "):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0].strip()
    return cleaned


def _relationship_type(title: str) -> str:
    lower = title.lower()
    if any(term in lower for term in ("recruiter", "talent acquisition", "sourcer")):
        return "recruiter_intro"
    if any(term in lower for term in ("head of product", "director", "vp", "chief product")):
        return "hiring_manager_intro"
    if any(term in lower for term in ("product manager", "product owner", "platform pm", "technical pm")):
        return "peer_conversation"
    return "follow_only"


def _trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "."


def _clean_excerpt(text: str) -> str:
    text = _strip_date_prefix(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


_DATE_RE = re.compile(r"^([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})\s+·")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def _post_date(description: str) -> date | None:
    """Parse the leading date from a LinkedIn search snippet, e.g. 'Mar 16, 2026 ·'."""
    m = _DATE_RE.match(description or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
    except (KeyError, ValueError):
        return None


def _is_recent_post(description: str, max_age_days: int = 28) -> bool:
    """True when the post date is within max_age_days, or when no date can be parsed."""
    post_dt = _post_date(description)
    if post_dt is None:
        return True
    return (date.today() - post_dt).days <= max_age_days


def _strip_date_prefix(description: str) -> str:
    """Remove leading 'MMM D, YYYY · ' from a LinkedIn search snippet."""
    return _DATE_RE.sub("", description or "").lstrip()


_LOGIN_WALL_PHRASES = (
    "agree & join linkedin",
    "sign in to linkedin",
    "join linkedin",
    "by clicking continue",
    "by clicking agree",
)


def _is_login_wall(description: str) -> bool:
    """True when the search snippet is a LinkedIn auth page rather than post content."""
    lower = (description or "").lower()
    return any(phrase in lower for phrase in _LOGIN_WALL_PHRASES)


def _message_variants(name: str, role_context: str, description: str, max_words: int) -> list[str]:
    first_name = name.split()[0] if name else "there"
    role_part = role_context
    for sep in (" - ", " | ", " @ "):
        if sep in role_context:
            role_part = role_context.split(sep, 1)[1].strip()
            break
    detail = description.strip()[:120].rstrip(".,;:") if description else ""
    variants = [
        _trim_words(
            f"Hi {first_name}, I came across your profile"
            + (f" — {detail}" if detail else f" and your work as {role_part}")
            + ". I work in technical product ownership across AI, speech, and platform"
            " products. Would be glad to connect.",
            max_words,
        ),
        _trim_words(
            f"Hi {first_name}, your background as {role_part} is close to what I work on"
            " in technical product ownership across AI, speech, and platform products."
            " Would be glad to follow your perspective here.",
            max_words,
        ),
    ]
    return variants


def _fallback_payload(raw_results: list[dict], config: dict) -> dict:
    """Keep discovery useful when the model returns malformed JSON."""
    discovery = config.get("engagement_discovery", {})
    networking = config.get("networking", {})
    people_limit = int(networking.get("suggestions_per_run", 8))
    posts_limit = int(discovery.get("posts_per_run", 8))
    max_message_words = int(networking.get("max_message_words", 70))
    people: list[dict] = []
    posts: list[dict] = []

    for item in raw_results:
        url = item.get("url", "")
        title = _clean_title(item.get("title", ""))
        description = item.get("description", "")
        topic = _topic_from_query(item.get("query", ""))
        entry = {
            "url": url,
            "why_relevant": description[:240],
        }
        if "/in/" in url and len(people) < people_limit:
            name = _person_name(title)
            people.append({
                **entry,
                "name": name,
                "role_or_context": title,
                "relationship_type": _relationship_type(title),
                "suggested_action": "review manually",
                "message_variants": _message_variants(name, title, description, max_message_words),
            })
        elif "/posts/" in url and len(posts) < posts_limit:
            posts.append({
                **entry,
                "author_or_source": title,
                "topic": topic,
                "suggested_comment": "",
            })

    return {"people": people, "posts": posts}


def _collect_results(config: dict) -> list[dict]:
    discovery = config.get("engagement_discovery", {})
    region = discovery.get("region", {})
    topics = discovery.get("topics", [])
    domains = discovery.get("linkedin_domains", {})
    results_per_query = int(discovery.get("results_per_query", 5))

    collected: list[dict] = []
    seen = set()
    for topic in topics:
        queries = [
            f'site:{domains.get("people", "linkedin.com/in")} "{topic}"',
            f'site:{domains.get("posts", "linkedin.com/posts")} "{topic}"',
        ]
        for query in queries:
            for item in search_web(query, region, count=results_per_query):
                url = item.get("url", "")
                if not url or url in seen:
                    continue
                description = item.get("description", "")
                if _is_login_wall(description):
                    continue
                if "/posts/" in url and not _is_recent_post(description):
                    continue
                seen.add(url)
                collected.append({"query": query, **item})
    return collected


def _render_people(items: list[dict]) -> str:
    if not items:
        return "_No people suggestions returned._"
    sections = []
    for item in items:
        messages = item.get("message_variants") or []
        if isinstance(messages, list):
            messages_text = "\n".join(f"  - {msg}" for msg in messages)
        else:
            messages_text = f"  - {messages}"
        sections.append(
            f"""### {item.get('name', 'Unknown person')}

- Role/context: {item.get('role_or_context', '')}
- Link: {item.get('url', '')}
- Why relevant: {item.get('why_relevant', '')}
- Relationship type: {item.get('relationship_type', '')}
- Suggested action: {item.get('suggested_action', 'review manually')}
- Ask readiness: cold
- Message variants:
{messages_text}
"""
        )
    return "\n\n".join(sections)


def _render_posts(items: list[dict]) -> str:
    if not items:
        return "_No post suggestions returned._"
    sections = []
    for item in items:
        comment = _trim_words(str(item.get("suggested_comment", "")).strip(), 40)
        raw_desc = item.get("why_relevant", "")
        excerpt = _clean_excerpt(raw_desc)
        post_dt = _post_date(raw_desc)
        lines = [
            f"### {item.get('author_or_source', 'Post to review')}",
            "",
        ]
        if post_dt:
            lines.append(f"- Posted: {post_dt.strftime('%b')} {post_dt.day}, {post_dt.year}")
        lines.append(f"- Topic: {item.get('topic', '')}")
        lines.append(f"- Link: {item.get('url', '')}")
        lines.append(f"- Excerpt: {excerpt}")
        if comment:
            lines.append(f"- Draft comment: {comment}")
        lines.append("")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def discover(config_path: Path | None = None) -> dict:
    config = load_linkedin_config(config_path)
    raw_results = _collect_results(config)
    if not raw_results:
        logger.warning("[linkedin] No LinkedIn search results found.")
        return {"people": [], "posts": []}

    discovery = config.get("engagement_discovery", {})
    networking = config.get("networking", {})
    post_results = [r for r in raw_results if "/posts/" in r.get("url", "")]
    people_results = [r for r in raw_results if "/in/" in r.get("url", "")]
    prompt = PROMPT.format(
        positioning=config.get("positioning", ""),
        target_people=format_yaml_list(networking.get("target_people", [])),
        topics=format_yaml_list(discovery.get("topics", [])),
        max_message_words=int(networking.get("max_message_words", 70)),
        forbidden_phrases=format_yaml_list(config.get("forbidden_phrases", [])),
        posts=format_yaml_list([
            f"{item.get('title', '')} | {item.get('url', '')} | {_strip_date_prefix(item.get('description', ''))}"
            for item in post_results[:20]
        ]),
        people=format_yaml_list([
            f"{item.get('title', '')} | {item.get('url', '')} | {item.get('description', '')}"
            for item in people_results[:20]
        ]),
    )
    try:
        payload = extract_json(complete_linkedin(SYSTEM, prompt))
    except Exception as exc:
        logger.warning(
            "[linkedin] Could not parse discovery JSON; writing raw review queue instead: %s",
            exc,
        )
        payload = _fallback_payload(raw_results, config)
    if not isinstance(payload, dict):
        raise ValueError("Discovery response must be a JSON object")

    people = list(payload.get("people", []))[: int(networking.get("suggestions_per_run", 8))]
    posts = []
    for item in list(payload.get("posts", [])):
        if not isinstance(item, dict):
            continue
        item = dict(item)
        comment = str(item.get("suggested_comment", "")).strip()
        if not comment:
            continue
        item["suggested_comment"] = _trim_words(comment, 40)
        posts.append(item)
        if len(posts) >= int(discovery.get("posts_per_run", 8)):
            break

    append_section(
        configured_path(config, "networking"),
        f"## {today_slug()}\n\n{_render_people(people)}",
    )
    append_section(
        configured_path(config, "engagement"),
        f"## {today_slug()}\n\n{_render_posts(posts)}",
    )
    logger.info("[linkedin] Added %s people and %s post suggestions.", len(people), len(posts))
    return {"people": people, "posts": posts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover LinkedIn engagement and networking suggestions.")
    parser.add_argument("--config", type=Path, help="Path to linkedin/config.yml")
    args = parser.parse_args()
    discover(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
