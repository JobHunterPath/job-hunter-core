"""
Job hunt pipeline orchestrator.

Two modes, one entry point:

  hunt (default)   Scrape jobs from configured companies and boards.
                   Runs daily via GitHub Actions.

  tailor-links     Tailor resume for a specific list of URLs.
                   Pass --links "URL1, URL2" or set TAILOR_LINKS env var.
                   Discovered companies are registered to search_config.yml regions.
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

from core.config import ROOT as REPO_ROOT
from core.config import load_api_config, profile_path, setup_logging
from core.url_liveness import UrlLivenessCache
from core.utils import title_matches
from pipeline.company_registry import extract_career_url, register_company
from pipeline.cover_writer import write_cover
from pipeline.enrichment import drop_dead_urls_before_enrichment, enrich_snippets
from pipeline.pdf_compiler import compile_tex
from pipeline.readme_writer import slugify
from pipeline.readme_writer import update_readme as write_readme_table
from pipeline.scorer import filter_matches
from pipeline.tailorer import tailor
from pipeline.validator import validate
from sources.jd_fetcher import fetch_jd, jd_from_text
from sources.scraper import scrape
from sources.search_providers import canonicalize_url
from tracking.tracker import filter_new_jobs, load_processed, mark_processed

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

TODAY = datetime.today().strftime("%Y-%m-%d")
MAX_TAILORING_PER_RUN = 15

ROOT = str(REPO_ROOT)
JOBS_DIR = profile_path("output_dir", "jobs")
JOBS_DIR.mkdir(exist_ok=True)


def _parse_urls(raw: str) -> list[str]:
    """Split a comma- or newline-separated string of URLs into a clean list."""
    return [
        token.strip()
        for token in raw.replace(",", "\n").splitlines()
        if token.strip() and not token.strip().startswith("#")
    ]


def _load_search_rules() -> tuple[list[str], list[str]]:
    """Return configured accepted job titles and excluded title terms."""
    search_cfg_path = Path(ROOT) / "config" / "search_config.yml"
    try:
        data = yaml.safe_load(search_cfg_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return [], []

    title_filters = data.get("global_search", {}).get("job_titles", [])
    excluded_title_terms = data.get("exclusion_rules", {}).get("excluded_title_terms", [])
    return title_filters, excluded_title_terms


def update_readme(matches: list[dict]) -> None:
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


def _jobs_from_hunt(region: str | None = None) -> tuple[list[dict], set, set]:
    """Scrape configured companies/boards, then deduplicate against processed jobs."""
    jobs = scrape(region=region)
    if not jobs:
        return [], set(), set()
    new_jobs, existing_urls, existing_titles = filter_new_jobs(jobs)
    seen_canonical: set[str] = set()
    deduped: list[dict] = []
    for job in new_jobs:
        c = canonicalize_url(job.get("url", ""))
        if not c or c not in seen_canonical:
            if c:
                seen_canonical.add(c)
            deduped.append(job)
    dropped = len(new_jobs) - len(deduped)
    if dropped:
        logger.info("[pipeline] Dropped %s canonical-URL duplicate(s) before enrichment", dropped)
    return deduped, existing_urls, existing_titles


def _jobs_from_links(raw: str, force: bool, existing_urls: set) -> list[dict]:
    """
    Fetch job descriptions from a list of direct URLs.

    Skips URLs already in applied_jobs.yml unless --force is set.
    Registers each new company to search_config.yml regions for future hunt runs.
    """
    jobs = []
    title_filters, excluded_title_terms = _load_search_rules()
    for url in _parse_urls(raw):
        if not force and url in existing_urls:
            logger.info("  [skip] Already processed (use --force to re-tailor): %s", url)
            continue
        job = fetch_jd(url)
        if job:
            if not title_matches(job.get("title", ""), title_filters, excluded_title_terms):
                logger.info(
                    "  [skip] Irrelevant title after JD extraction: %s @ %s",
                    job.get("title", "?"),
                    job.get("company", "?"),
                )
                continue
            _register_company(job)
            jobs.append(job)
            logger.info("  fetched: %s @ %s", job["title"], job["company"])
        else:
            logger.warning("  could not fetch JD: %s", url)
    return jobs


def _jobs_from_raw_text(
    text: str,
    title: str | None,
    company: str | None,
    force: bool,
    existing_urls: set,
) -> list[dict]:
    """Build a single job dict from raw pasted JD text."""
    job = jd_from_text(text, title=title, company=company)
    if not job:
        logger.error("[pipeline] Could not parse job from raw text.")
        return []
    if not force and job["url"] in existing_urls:
        logger.info("  [skip] Already processed (use --force to re-tailor): %s", job["url"])
        return []
    logger.info("  raw input: %s @ %s", job["title"], job["company"])
    return [job]


def _extract_career_url(job_url: str) -> str | None:
    return extract_career_url(job_url)


def _register_company(job: dict) -> None:
    register_company(job, ROOT)


def _enrich_snippets(jobs: list[dict], api_cfg: dict | None = None) -> list[dict]:
    return enrich_snippets(jobs, api_cfg, fetcher=fetch_jd)


def _drop_dead_urls_before_enrichment(
    jobs: list[dict],
    api_cfg: dict,
    url_checker=None,
) -> list[dict]:
    return drop_dead_urls_before_enrichment(
        jobs,
        api_cfg,
        url_checker=url_checker or UrlLivenessCache().is_alive,
    )


def _process_match(match: dict) -> bool:
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
    jobs: list[dict],
    *,
    skip_validate: bool,
    skip_score: bool,
    max_years: int,
    api_cfg: dict,
    url_checker=None,
) -> list[dict]:
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
        matches = filter_matches(jobs)
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
  python scripts/pipeline/orchestrator.py
  python scripts/pipeline/orchestrator.py --region berlin
  python scripts/pipeline/orchestrator.py --mode tailor-links --links "https://url1, https://url2"
  python scripts/pipeline/orchestrator.py --mode tailor-links --skip-score --force
  python scripts/pipeline/orchestrator.py --mode tailor-raw --jd "$(cat job.txt)"
  python scripts/pipeline/orchestrator.py --mode tailor-raw --jd - --title "Backend Engineer" --company Acme
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
        help=(
            "Raw job description text for tailor-raw mode. "
            "Pass '-' to read from stdin."
        ),
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
        help="Optional search_config.yml region key for hunt mode, e.g. berlin. Omit for all enabled regions.",
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
        logger.info("[pipeline] Step 1: Scraping and deduplicating jobs...")
        jobs, existing_urls, existing_titles = _jobs_from_hunt(args.region)
        if not jobs:
            logger.warning("[pipeline] No new jobs found. Exiting.")
            return 0

        jobs = _drop_dead_urls_before_enrichment(
            jobs,
            api_cfg,
            url_liveness.is_alive,
        )
        if not jobs:
            logger.warning("[pipeline] All scraped jobs failed URL verification before enrichment.")
            return 0

        logger.info("[pipeline] Step 1b: Enriching sparse job descriptions...")
        jobs = _enrich_snippets(jobs, api_cfg)

    elif args.mode == "tailor-links":
        raw_links = args.links or os.environ.get("TAILOR_LINKS", "")
        if not raw_links:
            logger.error(
                "[pipeline] No URLs provided. "
                "Use --links 'URL1, URL2' or set the TAILOR_LINKS environment variable."
            )
            return 1
        existing_urls, existing_titles = load_processed()
        logger.info("[pipeline] Step 1: Fetching job descriptions from links...")
        jobs = _jobs_from_links(raw_links, args.force, existing_urls)
        if not jobs:
            logger.warning("[pipeline] No jobs fetched. Exiting.")
            return 2

    else:  # tailor-raw
        raw_jd = args.jd
        if not raw_jd:
            logger.error(
                "[pipeline] No job description provided. "
                "Use --jd 'TEXT' or --jd - to read from stdin."
            )
            return 1
        if raw_jd == "-":
            raw_jd = sys.stdin.read()
        existing_urls, existing_titles = load_processed()
        logger.info("[pipeline] Step 1: Parsing raw job description...")
        jobs = _jobs_from_raw_text(raw_jd, args.title, args.company, args.force, existing_urls)
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
