"""
Job hunt pipeline orchestrator.

Two modes, one entry point:

  hunt (default)   Search all enabled job sources and boards for configured titles.
                   Runs daily via GitHub Actions.

  tailor-links     Tailor resume for a specific list of URLs.
                   Pass --links "URL1, URL2" or set TAILOR_LINKS env var.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any

import yaml

from job_hunter_core.core.config import ROOT as REPO_ROOT
from job_hunter_core.core.config import load_api_config, profile_path, setup_logging
from job_hunter_core.core.url_liveness import UrlLivenessCache
from job_hunter_core.pipeline.cover_writer import write_cover
from job_hunter_core.pipeline.enrichment import drop_dead_urls_before_enrichment  # noqa: F401
from job_hunter_core.pipeline.hunt_pipeline import (  # noqa: F401
    _jobs_from_hunt,
    load_hunt_snapshot,
    run_hunt,
    run_hunt_scrape_only,
)
from job_hunter_core.pipeline.pdf_compiler import compile_tex
from job_hunter_core.pipeline.readme_writer import slugify
from job_hunter_core.pipeline.readme_writer import update_readme as write_readme_table
from job_hunter_core.pipeline.scorer import filter_matches, strategic_override_companies
from job_hunter_core.pipeline.tailor_pipeline import (
    _jobs_from_links,  # noqa: F401
    _load_search_rules,  # noqa: F401
    run_tailor,
)
from job_hunter_core.pipeline.tailorer import tailor
from job_hunter_core.pipeline.validator import validate
from job_hunter_core.sources.jd_fetcher import fetch_jd
from job_hunter_core.tracking.tracker import mark_processed

if TYPE_CHECKING:
    from pathlib import Path

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

TODAY = datetime.today().strftime("%Y-%m-%d")
MAX_TAILORING_PER_RUN = 15

ROOT = str(REPO_ROOT)
JOBS_DIR = profile_path("output_dir", "jobs")
JOBS_DIR.mkdir(exist_ok=True)


def _enrich_snippets(
    jobs: list[dict[str, Any]], api_cfg: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    from job_hunter_core.pipeline.enrichment import enrich_snippets

    return enrich_snippets(jobs, api_cfg, fetcher=fetch_jd)


def update_readme(matches: list[dict[str, Any]]) -> None:
    write_readme_table(matches, ROOT, TODAY)


def _copy_latex_assets(job_dir: Path) -> None:
    for src in (
        profile_path("latex_class", "altacv.cls"),
        profile_path("profile_image", ""),
    ):
        if src.exists():
            shutil.copy2(src, job_dir / src.name)


def _make_generated_tex_self_contained(tex: str) -> str:
    latex_class = profile_path("latex_class", "altacv.cls")
    profile_image = profile_path("profile_image", "")

    if latex_class.exists() or latex_class.name:
        class_stem = re.escape(latex_class.stem)
        tex = re.sub(
            rf"(\\documentclass(?:\[[^\]]*\])?)\{{(?:[./\\]+)?(?:.*[./\\])?{class_stem}\}}",
            rf"\1{{{latex_class.stem}}}",
            tex,
            count=1,
        )

    if profile_image.exists() or profile_image.name:
        image_stem = re.escape(profile_image.stem)
        tex = re.sub(
            rf"(\\photoR\{{[^}}]+\}})\{{(?:[./\\]+)?(?:.*[./\\])?{image_stem}\}}",
            rf"\1{{{profile_image.stem}}}",
            tex,
            count=1,
        )

    return tex


def _process_match(match: dict[str, Any]) -> bool:
    """
    Tailor, compile PDF, and write cover letter for a single matched job.
    Returns True on full success, False if a critical step fails.
    PDF compilation is non-critical; failure there does not abort the job.
    """
    job = match["job"]
    slug = f"{TODAY}_{slugify(job['company'])}_{slugify(job['title'])}"
    job_dir = JOBS_DIR / slug
    job_dir.mkdir(exist_ok=True)

    meta = {
        "date": TODAY,
        "title": job["title"],
        "company": job["company"],
        "url": job["url"],
        "location": job.get("location", ""),
        "posted": job.get("posted", ""),
        "score": match["score"],
        "matched_keywords": match.get("matched_keywords", []),
        "gaps": match.get("gaps", []),
        "source": job.get("source", "scraped"),
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (job_dir / "jd.md").write_text(
        f"# {job['title']} @ {job['company']}\n\n"
        f"**URL:** {job['url']}\n\n"
        f"**Location:** {job.get('location', 'Unknown')}\n\n"
        f"**Posted:** {job.get('posted', 'Unknown')}\n\n"
        f"{job['snippet']}",
        encoding="utf-8",
    )

    logger.info("  Tailoring resume...")
    try:
        tex_path = job_dir / "resume_tailored.tex"
        tex_path.write_text(_make_generated_tex_self_contained(tailor(match)), encoding="utf-8")
        _copy_latex_assets(job_dir)
        logger.info("  resume tailored")
    except Exception as e:
        logger.error("  tailoring failed: %s", e)
        return False

    logger.info("  Compiling PDF...")
    try:
        pdf = compile_tex(str(tex_path), str(job_dir))
        logger.info("  PDF %s", "generated" if pdf else "(LaTeX saved, no PDF)")
    except Exception as e:
        logger.warning("  PDF compilation failed: %s - continuing", e)

    logger.info("  Writing cover letter...")
    try:
        write_cover(match, str(job_dir))
        logger.info("  cover letter written")
    except Exception as e:
        logger.error("  cover letter failed: %s", e)
        return False

    logger.info("  complete -> jobs/%s/", slug)
    return True


def _process_jobs(
    jobs: list[dict[str, Any]],
    *,
    skip_validate: bool,
    skip_score: bool,
    max_years: int,
    api_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    url_checker: Any = None,
) -> list[dict[str, Any]]:
    """
    Shared downstream pipeline: validate, score, tailor, cover, PDF.
    Returns the list of successfully processed match dicts.
    """
    if not skip_validate:
        logger.info("[pipeline] Validating %s job(s)...", len(jobs))
        jobs, rejected = validate(
            jobs,
            max_years=max_years,
            api_cfg=api_cfg,
            url_checker=url_checker or UrlLivenessCache().is_alive,
            max_years_bypass_companies=strategic_override_companies(scoring_cfg),
        )
        for job in rejected:
            logger.info(
                "  Rejected: %s @ %s: %s",
                job.get("title"),
                job.get("company"),
                job.get("_rejection_reason"),
            )
        if not jobs:
            logger.warning("[pipeline] All jobs rejected during validation.")
            return []
        logger.info("[pipeline] %s job(s) passed validation", len(jobs))
    else:
        logger.info("[pipeline] Validation skipped (--skip-validate)")

    if skip_score:
        logger.info("[pipeline] Scoring skipped (--skip-score) - processing all")
        matches = [{"job": job, "score": 0, "matched_keywords": [], "gaps": []} for job in jobs]
    else:
        logger.info("[pipeline] Scoring %s job(s)...", len(jobs))
        matches = filter_matches(jobs, config=scoring_cfg)
        if not matches:
            logger.warning("[pipeline] No jobs passed the scoring threshold.")
            return []
        logger.info("[pipeline] %s job(s) passed scoring", len(matches))

    if len(matches) > MAX_TAILORING_PER_RUN:
        matches = sorted(matches, key=lambda match: match.get("score", 0), reverse=True)
        logger.info(
            "[pipeline] Hard limit: tailoring top %s of %s matched job(s)",
            MAX_TAILORING_PER_RUN,
            len(matches),
        )
        matches = matches[:MAX_TAILORING_PER_RUN]

    logger.info("[pipeline] Processing %s matched job(s)...", len(matches))
    processed = []
    for idx, match in enumerate(matches, 1):
        job = match["job"]
        logger.info(
            "[pipeline] [%s/%s] %s @ %s (score=%s)",
            idx,
            len(matches),
            job["title"],
            job["company"],
            match["score"],
        )
        try:
            if _process_match(match):
                processed.append(match)
        except Exception as e:
            logger.error("  Unexpected error: %s", e, exc_info=True)

    return processed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Job hunt pipeline - hunt or tailor specific links/text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  job-hunter hunt
  job-hunter hunt --region primary
  job-hunter tailor-links --links "https://url1, https://url2"
  job-hunter tailor-links --skip-score --force
  job-hunter tailor-raw --jd "$(cat job.txt)"
  job-hunter tailor-raw --jd - --title "Backend Engineer" --company Acme
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["hunt", "tailor-links", "tailor-raw"],
        default="hunt",
        help=(
            "hunt: scrape configured companies (default). "
            "tailor-links: process specific URLs. "
            "tailor-raw: tailor from pasted job description text."
        ),
    )
    parser.add_argument(
        "--links",
        metavar="URLS",
        help="Comma-separated job URLs for tailor-links mode. Falls back to TAILOR_LINKS env var.",
    )
    parser.add_argument(
        "--jd",
        metavar="TEXT",
        help=("Raw job description text for tailor-raw mode. Pass '-' to read from stdin."),
    )
    parser.add_argument(
        "--title",
        metavar="TITLE",
        help="Job title override for tailor-raw mode (skips LLM title extraction).",
    )
    parser.add_argument(
        "--company",
        metavar="COMPANY",
        help="Company name override for tailor-raw mode (skips LLM company extraction).",
    )
    parser.add_argument(
        "--region",
        help="Optional search_config.yml region key for hunt mode, e.g. primary. Omit for all enabled regions.",
    )
    hunt_split = parser.add_mutually_exclusive_group()
    hunt_split.add_argument(
        "--scrape-only",
        action="store_true",
        help="Run scrape, URL-check, and enrichment only; write snapshot and exit.",
    )
    hunt_split.add_argument(
        "--from-snapshot",
        metavar="PATH",
        help="Skip scraping; load enriched jobs from a scrape snapshot.",
    )
    parser.add_argument("--skip-score", action="store_true", help="Bypass scoring threshold")
    parser.add_argument("--skip-validate", action="store_true", help="Bypass validation checks")
    parser.add_argument("--force", action="store_true", help="Re-process already-tracked jobs")
    return parser


def run(args: argparse.Namespace) -> int:
    logger.info("\n%s", "=" * 60)
    region_label = args.region if args.mode == "hunt" and args.region else "all"
    logger.info("Pipeline | mode=%s | region=%s | %s", args.mode, region_label, TODAY)
    logger.info("%s", "=" * 60)

    api_cfg = load_api_config()
    url_liveness = UrlLivenessCache()
    scoring_cfg = yaml.safe_load(
        open(os.path.join(ROOT, "config", "scoring_config.yml"), encoding="utf-8")
    )
    max_years = scoring_cfg.get("scoring", {}).get("max_years_experience_required", 4)

    if args.mode == "hunt":
        if args.scrape_only:
            snapshot_path, count = run_hunt_scrape_only(
                args.region,
                REPO_ROOT,
                api_cfg,
                url_liveness.is_alive,
            )
            print(f"snapshot_path={snapshot_path.as_posix()}")
            print(f"candidate_count={count}")
            print(f"has_candidates={str(count > 0).lower()}")
            return 0

        if args.from_snapshot:
            jobs, existing_urls, existing_titles = load_hunt_snapshot(args.from_snapshot)
            if not jobs:
                logger.warning("[pipeline] Snapshot has no jobs. Exiting.")
                return 0
        else:
            jobs, existing_urls, existing_titles = run_hunt(
                args, api_cfg, scoring_cfg, url_liveness
            )
        if not jobs:
            return 0

    elif args.mode == "tailor-links":
        raw_links = args.links or os.environ.get("TAILOR_LINKS", "")
        if not raw_links:
            logger.error(
                "[pipeline] No URLs provided. "
                "Use --links 'URL1, URL2' or set the TAILOR_LINKS environment variable."
            )
            return 1
        jobs, existing_urls, existing_titles = run_tailor(args, api_cfg, scoring_cfg, url_liveness)
        if not jobs:
            logger.warning("[pipeline] No jobs fetched. Exiting.")
            return 2

    else:  # tailor-raw
        if not args.jd:
            logger.error(
                "[pipeline] No job description provided. "
                "Use --jd 'TEXT' or --jd - to read from stdin."
            )
            return 1
        jobs, existing_urls, existing_titles = run_tailor(args, api_cfg, scoring_cfg, url_liveness)
        if not jobs:
            logger.warning("[pipeline] No jobs parsed. Exiting.")
            return 2

    logger.info("[pipeline] %s job(s) ready for processing", len(jobs))

    processed = _process_jobs(
        jobs,
        skip_validate=args.skip_validate,
        skip_score=args.skip_score,
        max_years=max_years,
        api_cfg=api_cfg,
        scoring_cfg=scoring_cfg,
        url_checker=url_liveness.is_alive,
    )

    if processed:
        logger.info("[pipeline] Updating README and tracker...")
        update_readme(processed)
        mark_processed([match["job"] for match in processed], existing_urls, existing_titles)

    logger.info("\n%s", "=" * 60)
    logger.info("[pipeline] Done. %s job(s) processed.", len(processed))
    logger.info("%s\n", "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run(_build_parser().parse_args()))
