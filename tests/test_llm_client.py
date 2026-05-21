from collections import deque
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

from core import llm_client
from core.llm_client import LLMClient, _google_generation_config_kwargs


def _client_with_limit(requests_per_minute):
    client = LLMClient.__new__(LLMClient)
    client._provider = "test"
    client._raw = None
    client._requests_per_minute = requests_per_minute
    client._rate_lock = __import__("threading").Lock()
    client._call_timestamps = deque()
    return client


def test_throttle_noops_when_disabled(monkeypatch):
    client = _client_with_limit(0)
    sleep = MagicMock()
    monkeypatch.setattr("core.llm_client.time.sleep", sleep)

    client._throttle()

    sleep.assert_not_called()


def test_throttle_waits_when_window_is_full(monkeypatch):
    client = _client_with_limit(2)
    client._call_timestamps.extend([100.0, 101.0])
    sleep = MagicMock()
    times = iter([120.0, 160.1])
    monkeypatch.setattr("core.llm_client.time.monotonic", lambda: next(times))
    monkeypatch.setattr("core.llm_client.time.sleep", sleep)

    client._throttle()

    sleep.assert_called_once_with(40.0)
    assert list(client._call_timestamps) == [101.0, 160.1]


def test_get_llm_client_cache_is_thread_safe(monkeypatch):
    created = []
    config = {
        "llm": {
            "default_provider": "ollama",
            "providers": {"validation": "ollama"},
            "rate_limits": {"ollama": {"requests_per_minute": 4}},
        },
        "ollama": {"base_url": "http://localhost:11434"},
        "secrets": {},
    }

    class FakeClient:
        def __init__(self, provider, api_key="", base_url="", requests_per_minute=0):
            created.append((provider, api_key, base_url, requests_per_minute))

    monkeypatch.setattr("core.config.load_api_config", lambda: config)
    monkeypatch.setattr("core.config.get_secret", lambda *args, **kwargs: "")
    monkeypatch.setattr(llm_client, "LLMClient", FakeClient)
    monkeypatch.setattr(llm_client, "_cache", {})

    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _: llm_client.get_llm_client("validation"), range(20)))

    assert len(created) == 1
    assert len({id(client) for client in clients}) == 1
    assert created == [("ollama", "", "http://localhost:11434", 4)]


def test_google_json_response_format_sets_mime_type():
    kwargs = _google_generation_config_kwargs("system", 20, "json")

    assert kwargs["max_output_tokens"] == 20
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["system_instruction"] == "system"
