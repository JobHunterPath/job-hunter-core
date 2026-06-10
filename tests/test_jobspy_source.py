from types import SimpleNamespace
from unittest.mock import patch

from job_hunter_core.sources.jobspy_source import JobSpySource, fetch_jobspy_jobs

_JOBSPY_CFG = {
    "http": {
        "job_boards": {
            "jobspy": {
                "enabled": True,
                "results_per_query": 20,
                "hours_old": 72,
                "glassdoor_enabled": False,
                "linkedin_enabled": False,
                "linkedin_fetch_description": False,
            }
        }
    }
}


class _Rows:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not rows

    def iterrows(self):
        return iter(enumerate(self._rows))


def test_bayt_searches_internationally_then_filters_by_region(monkeypatch):
    calls = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        if kwargs["site_name"] == ["bayt"]:
            return _Rows(
                [
                    {
                        "title": "Product Manager",
                        "company": "MuscatCo",
                        "job_url": "https://www.bayt.com/job/1",
                        "location": "Muscat, Oman",
                        "site": "bayt",
                    },
                    {
                        "title": "Product Manager",
                        "company": "DubaiCo",
                        "job_url": "https://www.bayt.com/job/2",
                        "location": "Dubai, UAE",
                        "site": "bayt",
                    },
                ]
            )
        return _Rows([])

    monkeypatch.setitem(
        __import__("sys").modules, "jobspy", SimpleNamespace(scrape_jobs=fake_scrape_jobs)
    )

    with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_JOBSPY_CFG):
        jobs = fetch_jobspy_jobs(
            ["Product Manager"],
            {"oman": {"country": "OM", "location": "Muscat"}},
            {"exclusion_rules": {"excluded_title_terms": []}},
        )

    assert calls[0]["site_name"] == ["google", "indeed"]
    assert calls[0]["location"] == "Muscat"
    assert calls[1]["site_name"] == ["bayt"]
    assert calls[1]["location"] == ""
    assert [job["company"] for job in jobs] == ["MuscatCo"]


class TestJobSpySource:
    def test_name(self):
        assert JobSpySource().name == "jobspy"

    def test_is_enabled_false_when_disabled(self):
        disabled = {"http": {"job_boards": {"jobspy": {"enabled": False}}}}
        with patch(
            "job_hunter_core.sources.jobspy_source.load_api_config", return_value=disabled
        ):
            assert JobSpySource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self, monkeypatch):
        from job_hunter_core.models import JobPosting

        fake_row = {
            "title": "Software Engineer",
            "company": "SpyCo",
            "job_url": "https://jobspy.com/1",
            "date_posted": "2026-06-01",
            "description": "A role.",
            "site": "google",
        }

        class _Rows:
            empty = False

            def iterrows(self):
                return iter([(0, fake_row)])

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=lambda **kw: _Rows()),
        )

        cfg = {
            "http": {
                "job_boards": {
                    "jobspy": {
                        "enabled": True,
                        "results_per_query": 5,
                        "hours_old": 72,
                        "glassdoor_enabled": False,
                        "linkedin_enabled": False,
                        "linkedin_fetch_description": False,
                    }
                }
            }
        }
        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=cfg):
            jobs = JobSpySource().fetch(
                ["Software Engineer"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {"exclusion_rules": {"excluded_title_terms": []}},
            )
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobSpy/Google"
