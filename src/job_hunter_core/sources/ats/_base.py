from job_hunter_core.core.config import get_timeout, load_api_config

_TIMEOUT = get_timeout("ats_scraper")
_ATS_CFG = load_api_config().get("http", {}).get("ats_scraper", {}) or {}
_SNIPPET_CHARS = int(_ATS_CFG.get("snippet_chars", 2000))
