"""
Provider-agnostic LLM client.

Supported providers: anthropic | openai | google | ollama

All providers expose the same complete() interface — callers don't know
or care which SDK is underneath. Configure per pipeline role in api_config.yml:

  llm:
    default_provider: anthropic
    providers:
      validation:   anthropic      # cheap/fast bulk calls
      tailoring:    openai         # override per role
    models:
      validation:   provider-model-name
      tailoring:    provider-model-name

Use get_llm_client(role) wherever a model call is needed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


def _google_generation_config_kwargs(
    system: str, max_tokens: int, response_format: str
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
    if response_format == "json":
        kwargs["response_mime_type"] = "application/json"
    if system:
        kwargs["system_instruction"] = system
    return kwargs


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "quota" in msg or "unavailable" in msg


class LLMClient:
    """
    Thin facade over provider SDKs (Strategy pattern).

    Each provider is a branch in complete() — add new providers by adding
    a branch in _init_client() and complete() without touching callers.
    """

    def __init__(
        self,
        provider: str,
        api_key: str = "",
        base_url: str = "",
        requests_per_minute: int = 0,
    ) -> None:
        self._provider = provider
        self._requests_per_minute = max(0, requests_per_minute)
        self._rate_lock = threading.Lock()
        self._call_timestamps: deque[float] = deque()
        self._raw = self._init_client(provider, api_key, base_url)

    # ── SDK construction ───────────────────────────────────────────────────────

    def _init_client(self, provider: str, api_key: str, base_url: str) -> Any:
        if provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError("python -m pip install anthropic") from None
            return Anthropic(api_key=api_key)

        if provider == "openai":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("python -m pip install openai") from None
            return OpenAI(api_key=api_key)

        if provider == "google":
            try:
                from google import genai
            except ImportError:
                raise ImportError("python -m pip install google-genai") from None
            return genai.Client(api_key=api_key)

        if provider == "ollama":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "python -m pip install openai  # Ollama uses the OpenAI-compatible API"
                ) from None
            # Ollama exposes an OpenAI-compatible endpoint; api_key is ignored server-side
            return OpenAI(
                base_url=base_url or "http://localhost:11434/v1",
                api_key="ollama",
            )

        raise ValueError(
            f"Unknown LLM provider: {provider!r}. Supported: anthropic | openai | google | ollama"
        )

    # ── Unified interface ──────────────────────────────────────────────────────

    def complete(
        self,
        *,
        system: str = "",
        user: str,
        model: str,
        max_tokens: int,
        max_retries: int = 3,
        response_format: str = "text",
        cache_system: bool = False,
        cache_ttl: str = "5m",
    ) -> str:
        """
        Send a prompt and return the response as a plain string.

        Args:
            system:       System / instruction prompt. May be empty.
            user:         User message content.
            model:        Provider-specific model identifier.
            max_tokens:   Maximum tokens to generate.
            max_retries:  Retry attempts on transient errors (rate limits, 5xx).
            cache_system: Anthropic only — add a cache breakpoint to the system prompt.
                          Requires the system text to be ≥ 1,024 tokens to be effective.
            cache_ttl:    Anthropic only — "5m" (default) or "1h" (extended, 2× write cost).
                          Use "1h" for sequential workflows that run longer than 5 minutes.

        Returns:
            Stripped response text.
        """
        logger.debug(f"[llm] provider={self._provider} model={model} max_tokens={max_tokens}")
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                self._throttle()
                return self._call(
                    system=system,
                    user=user,
                    model=model,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    cache_system=cache_system,
                    cache_ttl=cache_ttl,
                )
            except Exception as exc:
                if not _is_retryable(exc) or attempt == max_retries:
                    raise
                delay = 2**attempt
                logger.warning(
                    f"[llm] retryable error (attempt {attempt}/{max_retries}), retrying in {delay}s: {exc}"
                )
                time.sleep(delay)
                last_exc = exc
        raise last_exc  # unreachable but satisfies type checker

    def _throttle(self) -> None:
        if self._requests_per_minute <= 0:
            return

        window_seconds = 60.0
        while True:
            with self._rate_lock:
                now = time.monotonic()
                while self._call_timestamps and now - self._call_timestamps[0] >= window_seconds:
                    self._call_timestamps.popleft()

                if len(self._call_timestamps) < self._requests_per_minute:
                    self._call_timestamps.append(now)
                    return

                wait_seconds = window_seconds - (now - self._call_timestamps[0])

            time.sleep(max(wait_seconds, 0.1))

    def _call(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        response_format: str = "text",
        cache_system: bool = False,
        cache_ttl: str = "5m",
    ) -> str:

        if self._provider == "anthropic":
            kwargs: dict = dict(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": user}],
            )
            if system:
                if cache_system:
                    cache_ctrl: dict = {"type": "ephemeral"}
                    if cache_ttl == "1h":
                        cache_ctrl["ttl"] = "1h"
                    kwargs["system"] = [
                        {"type": "text", "text": system, "cache_control": cache_ctrl}
                    ]
                else:
                    kwargs["system"] = system
            resp = self._raw.messages.create(**kwargs)
            return resp.content[0].text.strip()

        if self._provider in ("openai", "ollama"):
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": user})
            kwargs: dict = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}
            resp = self._raw.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()

        if self._provider == "google":
            from google.genai import types

            config = types.GenerateContentConfig(
                **_google_generation_config_kwargs(system, max_tokens, response_format)
            )
            resp = self._raw.models.generate_content(
                model=model,
                contents=user,
                config=config,
            )
            return resp.text.strip()

        raise RuntimeError(f"[llm] Unhandled provider: {self._provider}")


# ── Factory with per-provider caching ─────────────────────────────────────────

_cache: dict[str, LLMClient] = {}
_cache_lock = threading.Lock()


def get_llm_client(role: str) -> LLMClient:
    """
    Return a cached LLMClient for the given pipeline role.

    Provider and credentials are resolved from api_config.yml.
    Clients are cached per provider — two roles sharing the same provider
    reuse the same connection object.

    Args:
        role: Pipeline stage name (validation | scoring | tailoring |
              cover_letter | discovery). Must match keys in api_config.yml.
    """
    from job_hunter_core.core.config import get_secret, load_api_config

    cfg = load_api_config()
    llm = cfg.get("llm", {})

    provider: str = llm.get("providers", {}).get(role) or llm.get("default_provider", "anthropic")

    with _cache_lock:
        if provider in _cache:
            return _cache[provider]

        secrets = cfg.get("secrets", {})
        provider_cfg = secrets.get(provider, {})

        if provider == "ollama":
            api_key = ""
            base_url = cfg.get("ollama", {}).get("base_url", "http://localhost:11434")
        else:
            env_var = provider_cfg.get("env_var", "")
            required = provider_cfg.get("required", False)
            api_key = get_secret(env_var, required=required) if env_var else ""
            base_url = ""

        rate_cfg = llm.get("rate_limits", {}).get(provider, {}) or {}
        requests_per_minute = int(rate_cfg.get("requests_per_minute", 0) or 0)

        logger.info(f"[llm] Initialising {provider} client (role: {role})")
        client = LLMClient(
            provider,
            api_key=api_key,
            base_url=base_url,
            requests_per_minute=requests_per_minute,
        )
        _cache[provider] = client
        return client
