import os
import tempfile
import textwrap
from pathlib import Path

# Must be set before any module is imported; core/config.py reads these at module level.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("BRAVE_API_KEY", "test-brave-key")
os.environ.setdefault("RAPIDAPI_KEY", "test-rapidapi-key")

if not (Path.cwd() / "config" / "api_config.yml").exists():
    runtime_root = Path(tempfile.mkdtemp(prefix="job-hunter-test-root-"))
    config_dir = runtime_root / "config"
    config_dir.mkdir(parents=True)

    (config_dir / "api_config.yml").write_text(
        textwrap.dedent(
            """
            secrets:
              anthropic:
                env_var: ANTHROPIC_API_KEY
                required: false
              openai:
                env_var: OPENAI_API_KEY
                required: false
              google:
                env_var: GOOGLE_API_KEY
                required: false
              brave:
                env_var: BRAVE_API_KEY
                required: false
              tavily:
                env_var: TAVILY_API_KEY
                required: false
              exa:
                env_var: EXA_API_KEY
                required: false
              rapidapi:
                env_var: RAPIDAPI_KEY
                required: false

            llm:
              provider: anthropic
              providers:
                validation: anthropic
                scoring: anthropic
                tailoring: anthropic
                cover_letter: anthropic
                jd_extraction: anthropic
                discovery: anthropic
              models:
                validation: claude-3-5-haiku-latest
                scoring: claude-3-5-haiku-latest
                tailoring: claude-3-5-haiku-latest
                cover_letter: claude-3-5-haiku-latest
                jd_extraction: claude-3-5-haiku-latest
                discovery: claude-3-5-haiku-latest
              max_tokens:
                validation: 256
                scoring: 256
                tailoring: 1024
                cover_letter: 1024
                jd_extraction: 512
                discovery: 512
              max_workers: 2

            http:
              url_verification:
                enabled: true
                timeout_seconds: 5
                max_workers: 2
              ats_discovery:
                timeout_seconds: 10
              search_providers:
                timeout_seconds: 10
                max_consecutive_failures: 3
                order:
                  - searxng
                  - brave
                searxng_base_url: "http://127.0.0.1:8080"
              playwright:
                timeout_seconds: 10
              ats_scraper:
                timeout_seconds: 10
              jd_enrichment:
                timeout_seconds: 10
                max_workers: 2
                skip_url_patterns: []
              url_liveness:
                timeout_seconds: 10
                max_consecutive_failures: 3
              job_boards:
                timeout_seconds: 10
                max_consecutive_failures: 3

            profile:
              resume_tex: resume.tex
              story_bank: story_bank.md
              project_instructions: project_instructions.md
              latex_class: altacv.cls
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (config_dir / "search_config.yml").write_text(
        "regions: {}\nscraping:\n  max_workers: 2\n",
        encoding="utf-8",
    )
    (config_dir / "scoring_config.yml").write_text("{}\n", encoding="utf-8")
    (config_dir / "tailoring_config.yml").write_text("{}\n", encoding="utf-8")
    (config_dir / "cover_letter_config.yml").write_text("{}\n", encoding="utf-8")
    (config_dir / "applied_jobs.yml").write_text("jobs: []\n", encoding="utf-8")
    (config_dir / "discovery_cache.yml").write_text("{}\n", encoding="utf-8")

    for filename in ("resume.tex", "story_bank.md", "project_instructions.md", "altacv.cls"):
        (runtime_root / filename).write_text("", encoding="utf-8")

    os.environ.setdefault("JOB_HUNTER_ROOT", str(runtime_root))

# src/ is on sys.path via the installed package (pip install -e .)
# No manual path manipulation needed.
