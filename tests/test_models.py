from __future__ import annotations

import pytest

from job_hunter_core.models import Company, JobPosting, JobScore


def _sample_posting() -> JobPosting:
    return JobPosting(
        title="Software Engineer",
        company="Acme Corp",
        url="https://acme.com/jobs/1",
        location="Berlin",
        snippet="Work on cool stuff",
        source="Greenhouse API",
        posted="2024-01-01",
        region="de",
        query="Software Engineer Berlin",
        extraction_method="ats_api",
        source_url="https://acme.com",
    )


def test_round_trip():
    jp = _sample_posting()
    assert JobPosting.from_dict(jp.to_dict()) == jp


def test_extra_keys_dropped():
    jp = _sample_posting()
    d = jp.to_dict()
    d["unknown_field"] = "should be dropped"
    result = JobPosting.from_dict(d)
    assert result == jp


def test_optional_fields_default():
    jp = JobPosting(
        title="Data Analyst",
        company="Beta Inc",
        url="https://beta.com/jobs/2",
        location="Remote",
        snippet="Analyse things",
        source="Lever API",
    )
    assert jp.posted == ""
    assert jp.region == ""
    assert jp.query == ""
    assert jp.extraction_method == ""
    assert jp.source_url == ""


def test_company_basic():
    c = Company(
        name="Gamma Ltd",
        career_url="https://gamma.com/careers",
        region="uk",
        location="London",
    )
    assert c.name == "Gamma Ltd"
    assert c.country == ""
    assert c.search_lang == ""
    assert c.ats == ""


def test_job_score_basic():
    js = JobScore(
        score=85,
        matched_keywords=["Python", "SQL"],
        gaps=["Kubernetes"],
    )
    assert js.score == 85
    assert js.matched_keywords == ["Python", "SQL"]
    assert js.gaps == ["Kubernetes"]
    assert js.years_exp_required is None


def test_job_score_with_years():
    js = JobScore(
        score=70,
        matched_keywords=["Go"],
        gaps=[],
        years_exp_required=3,
    )
    assert js.years_exp_required == 3
