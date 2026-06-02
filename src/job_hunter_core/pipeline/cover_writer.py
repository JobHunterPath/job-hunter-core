"""
Generates a cover letter (markdown) for each matched job.
Configurable via cover_letter_config.yml.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import yaml

from job_hunter_core.core.config import ROOT, profile_path
from job_hunter_core.core.llm_client import get_llm_client
from job_hunter_core.core.llm_utils import get_llm_role_settings

logger = logging.getLogger(__name__)

ROOT = str(ROOT)

# Load only the refined STAR stories section when present to avoid story-format
# examples being echoed in generated letters.
with open(profile_path("story_bank", "story_bank.md"), encoding="utf-8") as f:
    _raw_stories = f.read()

_FINAL_MARKER = "## Final — refined STAR stories"
_marker_idx = _raw_stories.find(_FINAL_MARKER)
if _marker_idx == -1:
    _marker_idx = _raw_stories.find("## Final - refined STAR stories")
STORIES = _raw_stories[_marker_idx:] if _marker_idx != -1 else _raw_stories


def _config_section(config: dict, name: str, default: dict | None = None) -> dict:
    """Read a section from either legacy top-level or nested cover_letter config."""
    if name in config:
        return config.get(name) or {}
    return (config.get("cover_letter", {}) or {}).get(name, default or {}) or {}


def _clean_body(body: str) -> str:
    """Remove citation-like story IDs if a model echoes them despite the prompt."""
    body = re.sub(r"\s*\[[A-Z][A-Z0-9_ -]*-\d+\]", "", body)
    return body.strip()


def load_cover_letter_config() -> dict[str, object]:
    config_file = os.path.join(ROOT, "config", "cover_letter_config.yml")
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info("[cover] Loaded cover letter configuration")
    return config


_SYSTEM = """You write professional cover letters for job applications.

Tone: formal, confident, and substantive. Not casual. Not sycophantic. Not salesy.

Hard rules — no exceptions:
- No em dashes (—). Rewrite the sentence instead.
- No casual phrases: "Happy to discuss", "Feel free to reach out", "I would love to", "Looking forward to connecting"
- No clichés: "I am passionate", "I am excited to apply", "I am honored", "I thrive in"
- No sycophancy: no praise of the company, no "your impressive mission", no flattery of any kind
- No mention of start dates, availability, or working hours
- No claims about fixing the company's problems
- No invented or extrapolated facts. Every metric and claim must appear explicitly in the story library. If it is not there, do not write it.
- No story IDs or bracketed citations, such as [STORY-01] or similar tags
- No sender details, address blocks, contact information, or Re: subject lines
- Return plain text only. No markdown, no headers, no bullet points.
- Start directly with the first sentence of the letter body."""

_PROMPT = """Write a professional cover letter body for this job application.

Structure (four paragraphs, plain text, no labels):

PARAGRAPH 1 — Background and role connection (2-3 sentences):
Open with a complete sentence stating the candidate's professional background and what they bring.
Connect it explicitly to what this specific role requires. Use full, grammatical sentences.
Example opening: "I have worked as a Technical Product Owner on [X] products, with [Y] background, which is directly relevant to this role."

PARAGRAPH 2 — Current/recent role (3-4 sentences):
Describe the environment: what the candidate owns and the scale of responsibility.
State 1-2 specific responsibilities using concrete language from the story library.
Include one specific outcome or result that is explicitly stated in the story library.
Begin with a complete sentence grounded in the candidate background and story library.

PARAGRAPH 3 — Earlier experience with verified outcomes (3-4 sentences):
Begin with: "Previously, ..." or "Earlier in my role, ..."
State the concrete scope: user count, team count, or stakeholder count as it appears in the story library.
State at least one verified metric outcome. Draw an explicit and specific parallel to a challenge in this role.

PARAGRAPH 4 — Specific interest in this company and role (2-3 sentences):
Begin with: "What draws me to this role is ..." or "This role is of interest because ..."
Make one concrete observation about what the company does or what the role involves, based on the job description.
State what aspect of the work aligns with how the candidate currently operates. No generic interest. No culture references.

CRITICAL CONSTRAINTS:
- Every factual claim must be directly traceable to the story library. Do not infer, extrapolate, or combine claims.
- No em dashes (—) anywhere in the output.
- No casual language. Professional register throughout.
- No story IDs or bracketed citations.
- Forbidden phrases: "I am passionate", "I am excited", "I am honored", "I am thrilled",
  "thank you for your time", "at your earliest convenience", "Happy to discuss",
  "I would love to", "Feel free to", any mention of start dates or availability.

CANDIDATE BACKGROUND:
{candidate_background}

STORY LIBRARY — use these facts and metrics exactly as stated, do not embellish:
{stories}

JOB DESCRIPTION:
{jd}

COMPANY: {company}
ROLE: {title}"""


def write_cover(
    match_result: dict,
    output_dir: str,
    config: dict | None = None,
) -> str:
    """
    Generate a cover letter (markdown) for a matched job.
    Returns the path to the saved cover_letter.md.
    """
    if config is None:
        config = load_cover_letter_config()

    job = match_result["job"]
    settings = get_llm_role_settings("cover_letter")

    header_config = _config_section(config, "header")
    if header_config.get("include_date", True):
        date_format = header_config.get("date_format", "%B %d, %Y")
        today = datetime.today().strftime(date_format).replace(" 0", " ")
    else:
        today = ""

    logger.info(f"[cover] Generating for {job['title']} @ {job['company']}")

    prompt = _PROMPT.format(
        stories=STORIES[:6000],
        jd=job["snippet"],
        company=job["company"],
        title=job["title"],
        candidate_background=(config.get("candidate_background") or "").strip()
        or (config.get("cover_letter", {}).get("candidate_background") or "").strip()
        or "Replace this with the candidate's current role, target positioning, and verified background.",
    )

    try:
        body = get_llm_client("cover_letter").complete(
            system=_SYSTEM,
            user=prompt,
            model=settings.model,
            max_tokens=settings.max_tokens,
        )
        body = _clean_body(body)
        logger.debug(f"[cover] Generated body ({len(body)} chars)")
    except Exception as e:
        logger.error(f"[cover] Error generating cover letter: {e}")
        raise

    header = _config_section(config, "header")
    salutation = header.get("salutation", "Dear Hiring Manager,")
    closing = _config_section(config, "closing")
    closing_format = closing.get("format", "Best regards,\nCandidate Name")

    date_line = f"{today}\n" if today else ""
    letter = f"{date_line}{salutation}\n\n{body}\n\n{closing_format}"

    md_path = os.path.join(output_dir, "cover_letter.md")
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(letter)
        logger.info(f"[cover] Saved: {md_path}")
    except Exception as e:
        logger.error(f"[cover] Error saving markdown: {e}")
        raise

    return md_path
