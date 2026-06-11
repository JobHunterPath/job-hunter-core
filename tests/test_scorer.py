"""Tests for pipeline/scorer.py — all LLM calls are mocked."""

import json
from unittest.mock import MagicMock, patch

from job_hunter_core.pipeline import scorer

CONFIG = {
    "scoring": {
        "min_fit_score": 80,
        "max_years_experience_required": 4,
        "strategic_overrides": [
            {"company": "Infineon", "reason": "strategic", "min_score_override": 75},
        ],
    },
}

JOB = {
    "title": "Product Manager",
    "company": "TestCo",
    "url": "https://testco.com/job",
    "snippet": "PM role with agile, roadmapping, stakeholder management.",
}


def _mock_client(text: str) -> MagicMock:
    """Return a mock LLMClient whose complete() returns text."""
    mock = MagicMock()
    mock.complete.return_value = text
    return mock


# ── check_strategic_override ────────────────────────────────────────────────


def test_strategic_override_matches():
    result = scorer.check_strategic_override({"company": "Infineon Technologies"}, CONFIG)
    assert result == 75


def test_strategic_override_no_match():
    result = scorer.check_strategic_override({"company": "Unknown Corp"}, CONFIG)
    assert result is None


# ── score() ─────────────────────────────────────────────────────────────────


def test_score_valid_response():
    payload = json.dumps(
        {
            "score": 85,
            "matched_keywords": ["agile", "roadmap"],
            "gaps": ["automotive"],
            "years_exp_required": 3,
        }
    )
    with patch(
        "job_hunter_core.pipeline.scorer.get_llm_client", return_value=_mock_client(payload)
    ):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 85
    assert result["matched_keywords"] == ["agile", "roadmap"]
    assert result["gaps"] == ["automotive"]
    assert result["job"] is JOB


def test_score_requests_json_response_format():
    payload = json.dumps(
        {
            "score": 85,
            "matched_keywords": ["agile"],
            "gaps": [],
            "years_exp_required": 3,
        }
    )
    mock = _mock_client(payload)

    with patch("job_hunter_core.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 85
    assert mock.complete.call_args.kwargs["response_format"] == "json"


def test_score_repairs_malformed_json_once():
    mock = MagicMock()
    mock.complete.side_effect = [
        '{"score": 85, "matched_keywords": ["Git',
        json.dumps(
            {
                "score": 85,
                "matched_keywords": ["Git"],
                "gaps": [],
                "years_exp_required": None,
            }
        ),
    ]

    with patch("job_hunter_core.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 85
    assert result["matched_keywords"] == ["Git"]
    assert mock.complete.call_count == 2
    assert "Convert this model response into valid JSON" in mock.complete.call_args.kwargs["user"]


def test_score_json_parse_error():
    with patch(
        "job_hunter_core.pipeline.scorer.get_llm_client", return_value=_mock_client("not json")
    ):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 0
    assert "parse error" in result["gaps"]
    assert result["job"] is JOB


def test_score_api_error():
    mock = MagicMock()
    mock.complete.side_effect = Exception("API down")
    with patch("job_hunter_core.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score(JOB, CONFIG)

    assert result["score"] == 0
    assert "api error" in result["gaps"]


# ── filter_matches() ─────────────────────────────────────────────────────────


def test_build_scoring_resume_context_compacts_latex_noise():
    resume = r"""
% hidden draft bullet
\documentclass{article}
\usepackage{hyperref}
\begin{document}
\section{Summary}
Product manager with roadmapping and stakeholder leadership.
\textbf{Skills}: agile, discovery, analytics
\end{document}
"""
    config = {
        "scoring": {
            "prompt_context": {
                "resume_mode": "compact_text",
                "resume_max_chars": 200,
            }
        }
    }

    context = scorer.build_scoring_resume_context(resume, config)

    assert "hidden draft bullet" not in context
    assert "documentclass" not in context
    assert "Product manager with roadmapping" in context
    assert "agile, discovery, analytics" in context


def test_score_uses_configured_resume_and_jd_context_caps(monkeypatch):
    payload = json.dumps(
        {
            "score": 85,
            "matched_keywords": ["agile"],
            "gaps": [],
            "years_exp_required": 3,
        }
    )
    captured = {}

    def complete(**kwargs):
        captured.update(kwargs)
        return payload

    mock = MagicMock()
    mock.complete.side_effect = complete
    config = {
        "scoring": {
            "prompt_context": {
                "resume_mode": "compact_text",
                "resume_max_chars": 80,
                "job_description_max_chars": 12,
            }
        }
    }

    monkeypatch.setattr(
        scorer,
        "BASE_RESUME",
        r"\documentclass{article}\begin{document}Roadmapping and agile leadership\end{document}",
    )

    with patch("job_hunter_core.pipeline.scorer.get_llm_client", return_value=mock):
        result = scorer.score({**JOB, "snippet": "ABCDEFGHIJKLMNO"}, config)

    assert result["score"] == 85
    # Resume context is now in the system prompt (cached prefix); JD stays in user message.
    system = captured["system"]
    assert "Roadmapping and agile leadership" in system
    user = captured["user"]
    assert "ABCDEFGHIJKL" in user
    assert "MNO" not in user


def _score_result(score_val, years=3, company="TestCo"):
    job = {**JOB, "company": company}
    return {
        "score": score_val,
        "matched_keywords": [],
        "gaps": [],
        "years_exp_required": years,
        "job": job,
    }


def test_filter_passes_above_threshold():
    with patch.object(scorer, "score", return_value=_score_result(85)):
        matches = scorer.filter_matches([JOB], config=CONFIG)
    assert len(matches) == 1


def test_filter_rejects_below_threshold():
    with patch.object(scorer, "score", return_value=_score_result(60)):
        matches = scorer.filter_matches([JOB], config=CONFIG)
    assert len(matches) == 0


def test_filter_rejects_too_many_years():
    with patch.object(scorer, "score", return_value=_score_result(90, years=10)):
        matches = scorer.filter_matches([JOB], config=CONFIG)
    assert len(matches) == 0


def test_filter_strategic_override_lowers_threshold():
    # 78 is below 80 but above Infineon's override of 75
    with patch.object(scorer, "score", return_value=_score_result(78, company="Infineon")):
        matches = scorer.filter_matches([{**JOB, "company": "Infineon"}], config=CONFIG)
    assert len(matches) == 1


def test_filter_strategic_override_still_fails_if_too_low():
    # 70 is below even Infineon's 75 override
    with patch.object(scorer, "score", return_value=_score_result(70, company="Infineon")):
        matches = scorer.filter_matches([{**JOB, "company": "Infineon"}], config=CONFIG)
    assert len(matches) == 0


def test_filter_null_years_not_rejected():
    result = _score_result(90)
    result["years_exp_required"] = None
    with patch.object(scorer, "score", return_value=result):
        matches = scorer.filter_matches([JOB], config=CONFIG)
    assert len(matches) == 1


# ── bypass_max_years_experience ──────────────────────────────────────────────

_BYPASS_CONFIG = {
    "scoring": {
        "min_fit_score": 80,
        "max_years_experience_required": 4,
        "strategic_overrides": [
            {
                "company": "Infineon",
                "reason": "strategic",
                "min_score_override": 75,
                "bypass_max_years_experience": True,
            },
            {
                "company": "SAP",
                "reason": "strategic",
                "min_score_override": 75,
                "bypass_max_years_experience": False,
            },
        ],
    },
}


def test_strategic_override_companies_respects_bypass_flag():
    result = scorer.strategic_override_companies(_BYPASS_CONFIG)
    assert "Infineon" in result
    assert "SAP" not in result


def test_strategic_override_companies_defaults_to_bypass_when_key_absent():
    cfg = {
        "scoring": {
            "strategic_overrides": [{"company": "Bosch", "reason": "x", "min_score_override": 70}]
        }
    }
    assert "Bosch" in scorer.strategic_override_companies(cfg)


def test_filter_strategic_company_bypasses_years():
    job = {**JOB, "company": "Infineon Technologies"}
    with patch.object(
        scorer, "score", return_value=_score_result(82, years=8, company="Infineon Technologies")
    ):
        matches = scorer.filter_matches([job], config=_BYPASS_CONFIG)
    assert len(matches) == 1


def test_filter_bypass_false_does_not_skip_years_check():
    job = {**JOB, "company": "SAP SE"}
    with patch.object(scorer, "score", return_value=_score_result(82, years=8, company="SAP SE")):
        matches = scorer.filter_matches([job], config=_BYPASS_CONFIG)
    assert len(matches) == 0
