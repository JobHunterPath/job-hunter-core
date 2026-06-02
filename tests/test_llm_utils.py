import pytest

from job_hunter_core.core.llm_utils import extract_json_object, get_llm_role_settings


def test_extract_json_object_strips_fence_and_preamble():
    raw = 'Here is the result:\n```json\n{"ok": true}\n```\nThanks'

    assert extract_json_object(raw) == '{"ok": true}'


def test_extract_json_object_ignores_trailing_json_like_text():
    raw = '{"title": "Product Manager"}\n{"debug": "ignored"}'

    assert extract_json_object(raw) == '{"title": "Product Manager"}'


def test_extract_json_object_accepts_array_payload():
    raw = 'Result:\n[{"title": "Product Owner"}]\nDone'

    assert extract_json_object(raw) == '[{"title": "Product Owner"}]'


def test_extract_json_object_returns_original_when_no_object():
    assert extract_json_object("not json") == "not json"


def test_get_llm_role_settings_uses_config_values():
    settings = get_llm_role_settings(
        "validation",
        api_cfg={
            "llm": {
                "models": {"validation": "configured-model"},
                "max_tokens": {"validation": 123},
            }
        },
    )

    assert settings.model == "configured-model"
    assert settings.max_tokens == 123


def test_get_llm_role_settings_requires_explicit_role_keys():
    with pytest.raises(KeyError, match="jd_extraction"):
        get_llm_role_settings(
            "jd_extraction",
            api_cfg={"llm": {"models": {}, "max_tokens": {}}},
        )
