from types import SimpleNamespace
from unittest.mock import patch

from job_hunter_core.sources.jobspy_source import JobSpySource

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
