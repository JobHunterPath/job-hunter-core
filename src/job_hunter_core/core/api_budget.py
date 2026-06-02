"""Local monthly hard quota guards for request-metered APIs."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import date
from pathlib import Path
from typing import Any

from job_hunter_core.core.config import ROOT, load_api_config

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DEFAULT_STATE_PATH = "config/api_usage.json"
_QUOTA_TEXT_MARKERS = (
    "quota",
    "credit",
    "billing",
    "payment",
    "usage exceeded",
    "usage limit",
    "subscription",
    "plan limit",
    "exceeded",
    "exhausted",
)


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def _budget_cfg(api_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    api_cfg = api_cfg or load_api_config()
    return api_cfg.get("http", {}).get("api_budgets", {}) or {}


def _state_path(cfg: dict[str, Any]) -> Path:
    configured = cfg.get("state_path") or _DEFAULT_STATE_PATH
    path = Path(str(configured))
    if not path.is_absolute():
        path = ROOT / path
    return path


def _provider_limit(provider: str, cfg: dict[str, Any]) -> int | None:
    limits = cfg.get("monthly_limits") or {}
    value = limits.get(provider)
    if value is None:
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        logger.warning("[api-budget] invalid monthly limit for %s: %r", provider, value)
        return None
    return limit if limit >= 0 else None


def _empty_state(month: str | None = None) -> dict[str, Any]:
    return {"month": month or current_month(), "providers": {}, "exhausted": {}}


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("[api-budget] rebuilding unreadable usage state %s: %s", path, exc)
        return _empty_state()

    if not isinstance(data, dict):
        return _empty_state()
    if not isinstance(data.get("providers"), dict):
        data["providers"] = {}
    if not isinstance(data.get("exhausted"), dict):
        data["exhausted"] = {}
    if data.get("month") != current_month():
        return _empty_state()
    return data


def _write_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _is_exhausted(provider: str, state: dict[str, Any]) -> bool:
    exhausted = state.setdefault("exhausted", {})
    return provider in exhausted


def _response_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        return None


def _response_text(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    text = getattr(response, "text", "") or ""
    if not text:
        try:
            text = str(exc)
        except Exception:
            text = ""
    return text.lower()


def is_api_quota_exhausted(exc: BaseException) -> bool:
    """Return True when an HTTP/API error clearly indicates monthly quota exhaustion."""
    status_code = _response_status(exc)
    if status_code in {402, 432}:
        return True
    if status_code not in {403, 429}:
        return False
    text = _response_text(exc)
    return any(marker in text for marker in _QUOTA_TEXT_MARKERS)


def _reason_from_error(exc: BaseException) -> str:
    status_code = _response_status(exc)
    if status_code is not None:
        return f"{status_code} {getattr(getattr(exc, 'response', None), 'reason', '')}".strip()
    return str(exc)[:120] or exc.__class__.__name__


def mark_api_exhausted(
    provider: str,
    *,
    reason: str | None = None,
    exc: BaseException | None = None,
    api_cfg: dict[str, Any] | None = None,
) -> None:
    """Disable a provider locally for the rest of the current month."""
    cfg = _budget_cfg(api_cfg)
    if not cfg.get("enabled", True):
        return

    provider_key = provider.lower().strip()
    if not provider_key:
        return

    with _LOCK:
        path = _state_path(cfg)
        state = _read_state(path)
        exhausted = state.setdefault("exhausted", {})
        if provider_key in exhausted:
            return

        reason_text = reason or (_reason_from_error(exc) if exc is not None else "quota exhausted")
        exhausted[provider_key] = {
            "reason": reason_text[:160],
            "marked_on": date.today().isoformat(),
        }
        _write_state(path, state)
        logger.warning(
            "[api-budget] %s disabled for %s after %s",
            provider_key,
            state["month"],
            reason_text,
        )


def reserve_api_call(provider: str, *, api_cfg: dict[str, Any] | None = None) -> bool:
    """Reserve one local monthly API call for provider.

    Returns False when a configured hard quota has already been reached.
    Providers without a configured limit are allowed and are not recorded.
    """
    cfg = _budget_cfg(api_cfg)
    if not cfg.get("enabled", True):
        return True

    provider_key = provider.lower().strip()
    limit = _provider_limit(provider_key, cfg)

    with _LOCK:
        path = _state_path(cfg)
        state = _read_state(path)
        if _is_exhausted(provider_key, state):
            marker = state["exhausted"].get(provider_key) or {}
            logger.warning(
                "[api-budget] %s disabled for %s (%s); skipping API call",
                provider_key,
                state["month"],
                marker.get("reason", "quota exhausted"),
            )
            return False

        if limit is None:
            return True

        providers = state.setdefault("providers", {})
        used = int(providers.get(provider_key, 0) or 0)
        if used >= limit:
            logger.warning(
                "[api-budget] %s monthly quota reached (%s/%s); skipping API call",
                provider_key,
                used,
                limit,
            )
            return False

        providers[provider_key] = used + 1
        _write_state(path, state)
        logger.debug(
            "[api-budget] reserved %s call %s/%s for %s",
            provider_key,
            providers[provider_key],
            limit,
            state["month"],
        )
        return True
