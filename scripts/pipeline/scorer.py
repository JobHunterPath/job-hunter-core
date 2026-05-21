"""
Score each job against the base resume using an LLM.
Scoring criteria are configurable via scoring_config.yml.
"""

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import yaml

from core.config import ROOT, load_api_config, profile_path
from core.llm_client import get_llm_client
from core.llm_utils import extract_json_object, get_llm_role_settings

logger = logging.getLogger(__name__)

# scripts/pipeline/ → scripts/ → repo root
with open(profile_path("resume_tex", "resume.tex"), encoding="utf-8") as f:
    BASE_RESUME = f.read()


def load_scoring_config() -> dict:
    """Load scoring configuration from scoring_config.yml."""
    config_file = ROOT / "config" / "scoring_config.yml"
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info("[scorer] Loaded scoring configuration")
    return config


SYSTEM = """You are a recruiter scoring job fit.
Return ONLY valid JSON with no markdown fences, no explanation.
Schema: {"score": int, "matched_keywords": [str], "gaps": [str], "years_exp_required": int or null}"""

PROMPT = """Score this candidate's resume against the job description.

RESUME CONTEXT:
{resume}

JOB DESCRIPTION:
{jd}

Rules:
- score: 0-100 fit score
- matched_keywords: up to 10 keywords from JD present in resume
- gaps: up to 5 skills in JD missing from resume
- years_exp_required: years of experience stated in JD, null if not mentioned

Return JSON only."""

REPAIR_PROMPT = """\
Convert this model response into valid JSON matching exactly this schema:
{{"score": int, "matched_keywords": [str], "gaps": [str], "years_exp_required": int|null}}

Rules:
- Return ONLY valid JSON.
- If a field is missing or unclear, use score=0, matched_keywords=[], gaps=["parse repair"], years_exp_required=null.

Response:
{raw}
"""


def _strip_latex_comments(tex: str) -> str:
    lines = []
    for line in tex.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        lines.append(line.split("%", 1)[0].rstrip())
    return "\n".join(lines)


def _compact_latex_resume(tex: str) -> str:
    text = _strip_latex_comments(tex)
    text = re.sub(r"\\(documentclass|usepackage|geometry|hypersetup)(?:\[[^\]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\(begin|end)\{[^}]*\}", "\n", text)
    text = re.sub(r"\\[a-zA-Z*]+(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _scoring_prompt_config(config: dict) -> dict:
    scoring = config.get("scoring", {}) or {}
    return scoring.get("prompt_context", {}) or {}


def build_scoring_resume_context(resume: str, config: dict) -> str:
    prompt_cfg = _scoring_prompt_config(config)
    mode = str(prompt_cfg.get("resume_mode", "compact_text"))
    max_chars = int(prompt_cfg.get("resume_max_chars", 4500))

    context = _compact_latex_resume(resume) if mode == "compact_text" else resume
    return context[:max_chars]


def build_scoring_job_context(job: dict, config: dict) -> str:
    prompt_cfg = _scoring_prompt_config(config)
    max_chars = int(prompt_cfg.get("job_description_max_chars", 5000))
    return str(job.get("snippet", ""))[:max_chars]


def _parse_score_json(raw: str) -> dict:
    result = json.loads(extract_json_object(raw))
    if not isinstance(result, dict):
        raise ValueError("scoring response must be a JSON object")
    return result


def score(job: dict, config: dict) -> dict:
    settings = get_llm_role_settings("scoring")
    resume_context = build_scoring_resume_context(BASE_RESUME, config)
    jd_context = build_scoring_job_context(job, config)
    prompt = PROMPT.format(resume=resume_context, jd=jd_context)

    try:
        raw = get_llm_client("scoring").complete(
            system=SYSTEM,
            user=prompt,
            model=settings.model,
            max_tokens=settings.max_tokens,
            response_format="json",
        )
        try:
            result = _parse_score_json(raw)
        except (json.JSONDecodeError, ValueError):
            logger.info("[scorer] Repairing malformed score JSON for %s", job.get("title", "Unknown"))
            repaired = get_llm_client("scoring").complete(
                system=SYSTEM,
                user=REPAIR_PROMPT.format(raw=raw[:2000]),
                model=settings.model,
                max_tokens=settings.max_tokens,
                response_format="json",
            )
            result = _parse_score_json(repaired)
        logger.debug(f"[scorer] {job.get('title', 'Unknown')} → score={result.get('score')}")
    except ImportError:
        raise  # missing SDK affects every job — let filter_matches fail fast
    except json.JSONDecodeError as e:
        logger.error(f"[scorer] JSON parse error: {e} | raw: {raw[:200]!r}")
        result = {"score": 0, "matched_keywords": [], "gaps": ["parse error"], "years_exp_required": None}
    except Exception as e:
        logger.error(f"[scorer] API error: {e}")
        result = {"score": 0, "matched_keywords": [], "gaps": ["api error"], "years_exp_required": None}

    result["job"] = job
    return result


def check_strategic_override(job: dict, config: dict) -> Optional[int]:
    """
    Check if a job matches a strategic override.
    Returns min_score_override or None if no override applies.
    """
    overrides = config.get("scoring", {}).get("strategic_overrides", [])
    job_company = job.get("company", "").lower()

    for override in overrides:
        if override.get("company", "").lower() in job_company:
            logger.info(f"[scorer] Strategic override for {job['company']}: {override['reason']}")
            return override.get("min_score_override")

    return None


def filter_matches(
    jobs: list[dict],
    min_score: Optional[int] = None,
    max_years: Optional[int] = None,
    config: Optional[dict] = None,
) -> list[dict]:
    """
    Score all jobs and return only those meeting the threshold.

    Args:
        jobs:      List of job postings to score.
        min_score: Minimum score override (reads from config if None).
        max_years: Max years of experience override (reads from config if None).
        config:    Scoring config dict (loads from file if None).

    Returns:
        List of scored match dicts for jobs that passed the threshold.
    """
    if config is None:
        config = load_scoring_config()

    scoring_config = config.get("scoring", {})
    if min_score is None:
        min_score = scoring_config.get("min_fit_score", 70)
    if max_years is None:
        max_years = scoring_config.get("max_years_experience_required", 4)

    logger.info(f"[scorer] Filtering jobs: min_score={min_score}, max_years={max_years}")

    # Fail fast if the LLM SDK isn't installed rather than silently scoring everything 0.
    try:
        get_llm_client("scoring")
    except ImportError as e:
        logger.error(f"[scorer] Cannot initialise scoring client — SDK missing: {e}")
        raise

    api_cfg = load_api_config()
    max_workers = int(api_cfg.get("llm", {}).get("max_workers", 5))

    counter = 0
    counter_lock = threading.Lock()

    def _score_job(job: dict) -> Optional[dict]:
        nonlocal counter
        with counter_lock:
            counter += 1
            idx = counter
        label = f"{job['title']} @ {job['company']}"
        prefix = f"[scorer] [{idx}/{len(jobs)}] {label}"
        logger.info(f"{prefix}: scoring...")
        result = score(job, config)
        score_val = result["score"]
        yrs = result.get("years_exp_required")
        logger.info(f"{prefix}: score={score_val}, years_required={yrs}")
        override_min = check_strategic_override(job, config)
        effective_min = override_min if override_min is not None else min_score
        if score_val < effective_min:
            logger.debug(f"{prefix}: skipped, score {score_val} below threshold {effective_min}")
            return None
        if yrs is not None and yrs > max_years:
            logger.debug(f"{prefix}: skipped, years required ({yrs}) exceeds maximum ({max_years})")
            return None
        logger.info(f"{prefix}: matched")
        return result

    matched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for result in executor.map(_score_job, jobs):
            if result is not None:
                matched.append(result)

    logger.info(f"[scorer] {len(matched)}/{len(jobs)} jobs matched threshold")
    return matched
