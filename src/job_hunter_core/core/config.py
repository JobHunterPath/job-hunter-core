"""
Config loader, secret resolution, and logging setup.

Secret lookup order:
  1. Environment variable (GitHub Actions — secret injected via workflow env:)
  2. System keychain via keyring (local runs — Credential Manager on Windows,
     Keychain on macOS, Secret Service on Linux)

Which environment variable names to look for is configured in config/api_config.yml
under the `secrets:` key — never hardcoded here. Actual secret values are never
stored in config files.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml


def _resolve_repo_root() -> Path:
    """Find the user workspace root, even when this code is installed."""
    env_root = os.environ.get("JOB_HUNTER_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(Path.cwd())
    candidates.append(Path(__file__).resolve().parents[2])

    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "config" / "api_config.yml").exists():
            return candidate

    return Path.cwd().resolve()


ROOT = _resolve_repo_root()
_ROOT = str(ROOT)

# Loaded once at import time; all callers use load_api_config() for the cached dict.
with open(os.path.join(_ROOT, "config", "api_config.yml"), encoding="utf-8") as _f:
    _API_CFG: dict = yaml.safe_load(_f)


def load_api_config() -> dict:
    """Return the cached api_config.yml contents."""
    return _API_CFG


def get_profile_config() -> dict:
    """
    Return repository-local profile file settings.

    The private repo can keep personal filenames, while the shared
    template repo can use neutral filenames without code changes.
    """
    return _API_CFG.get("profile", {})


def profile_path(key: str, default: str) -> Path:
    """Resolve a configured profile path relative to the repository root."""
    value = get_profile_config().get(key, default)
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def get_secret(env_var: str, required: bool = True) -> str:
    """
    Retrieve a secret by its environment-variable name.

    Lookup order:
      1. os.environ (GitHub Actions injects secrets here)
      2. keyring / system keychain (local runs)

    Args:
        env_var:  The environment variable name (e.g. "ANTHROPIC_API_KEY").
        required: Raise if the secret is not found anywhere.
    """
    value = os.environ.get(env_var)
    if value:
        return value

    try:
        import keyring

        value = keyring.get_password("job-hunt", env_var)
        if value:
            return value
    except Exception as e:
        if not required:
            return ""
        raise RuntimeError(
            f"keyring unavailable: {e}. Install with: python -m pip install keyring"
        ) from e

    if not required:
        return ""
    raise RuntimeError(
        f"Secret '{env_var}' not found.\n"
        f"  Local setup:\n"
        f'    python -c "import keyring; '
        f"keyring.set_password('job-hunt', '{env_var}', 'your-value')\"\n"
        f"  GitHub Actions: add '{env_var}' to repo Secrets and reference it\n"
        f"  in the workflow env: block. The name is set in config/api_config.yml."
    )


def setup_logging(log_level: str = "INFO", log_file: str = "job_hunt.log") -> logging.Logger:
    """
    Configure root logger so all submodule loggers propagate to the same
    console + rotating file handlers.
    """
    log_path = os.path.join(_ROOT, log_file)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = []

    for lib in (
        "urllib3",
        "requests",
        "httpx",
        "httpcore",
        "anthropic",
        "openai",
        "charset_normalizer",
    ):
        logging.getLogger(lib).setLevel(logging.WARNING)

    fmt_console = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fmt_file = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )

    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(fmt_console)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(fmt_file)
    root.addHandler(file_handler)

    logging.getLogger("job_hunt").info(f"Logging configured: level={log_level}, file={log_path}")
    return logging.getLogger("job_hunt")


# ── Eagerly load secrets that are always needed ───────────────────────────────
_secrets = _API_CFG.get("secrets", {})

BRAVE_API_KEY = get_secret(
    _secrets.get("brave", {}).get("env_var", "BRAVE_API_KEY"),
    required=_secrets.get("brave", {}).get("required", False),
)
TAVILY_API_KEY = get_secret(
    _secrets.get("tavily", {}).get("env_var", "TAVILY_API_KEY"),
    required=_secrets.get("tavily", {}).get("required", False),
)
EXA_API_KEY = get_secret(
    _secrets.get("exa", {}).get("env_var", "EXA_API_KEY"),
    required=_secrets.get("exa", {}).get("required", False),
)
RAPIDAPI_KEY = get_secret(
    _secrets.get("rapidapi", {}).get("env_var", "RAPIDAPI_KEY"),
    required=_secrets.get("rapidapi", {}).get("required", False),
)
ADZUNA_APP_ID = get_secret(
    _secrets.get("adzuna", {}).get("app_id_env_var", "ADZUNA_APP_ID"),
    required=False,
)
ADZUNA_API_KEY = get_secret(
    _secrets.get("adzuna", {}).get("api_key_env_var", "ADZUNA_API_KEY"),
    required=False,
)
REED_API_KEY = get_secret(
    _secrets.get("reed", {}).get("env_var", "REED_API_KEY"),
    required=False,
)
JOOBLE_API_KEY = get_secret(
    _secrets.get("jooble", {}).get("env_var", "JOOBLE_API_KEY"),
    required=False,
)


def get_timeout(section: str) -> int:
    """Return http.<section>.timeout_seconds from api_config.yml."""
    value = _API_CFG.get("http", {}).get(section, {}).get("timeout_seconds")
    if value is None:
        raise KeyError(f"Missing api_config.yml key: http.{section}.timeout_seconds")
    return int(value)


# ── Logging ───────────────────────────────────────────────────────────────────
logger = setup_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    log_file="job_hunt.log",
)
