"""Small helpers shared by LLM-backed pipeline stages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMRoleSettings:
    model: str
    max_tokens: int


def extract_json_object(raw: str) -> str:
    """Strip markdown fences and return the first complete JSON object or array."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = next((i for i in range(len(lines) - 1, 0, -1) if lines[i].strip() == "```"), None)
        text = "\n".join(lines[1:end] if end else lines[1:]).strip()

    starts = [idx for idx in (text.find("{"), text.find("[")) if idx != -1]
    if starts:
        start = min(starts)
        candidate = text[start:]
        try:
            _, end = json.JSONDecoder().raw_decode(candidate)
            return candidate[:end]
        except json.JSONDecodeError:
            object_start = text.find("{")
            object_end = text.rfind("}")
            if object_start != -1 and object_end != -1 and object_end > object_start:
                return text[object_start : object_end + 1]
    return text


def get_llm_role_settings(
    role: str,
    *,
    api_cfg: dict[str, Any] | None = None,
) -> LLMRoleSettings:
    """Return configured model and max token settings for a pipeline role."""
    if api_cfg is None:
        from job_hunter_core.core.config import load_api_config

        api_cfg = load_api_config()

    llm = api_cfg.get("llm", {}) or {}
    model = llm.get("models", {}).get(role)
    max_tokens = llm.get("max_tokens", {}).get(role)

    if not model:
        raise KeyError(f"Missing api_config.yml key: llm.models.{role}")
    if max_tokens is None:
        raise KeyError(f"Missing api_config.yml key: llm.max_tokens.{role}")

    return LLMRoleSettings(model=str(model), max_tokens=int(max_tokens))
