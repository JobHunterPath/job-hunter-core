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
        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=disabled):
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


_GLASSDOOR_CFG = {
    "http": {
        "job_boards": {
            "jobspy": {
                "enabled": True,
                "results_per_query": 5,
                "hours_old": 72,
                "glassdoor_enabled": True,
                "linkedin_enabled": False,
                "linkedin_fetch_description": False,
            }
        }
    }
}


class TestJobSpyCircuitBreaker:
    def test_403_disables_site_after_first_failure(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        glassdoor_calls = []

        def fake_scrape(site_name, **kw):
            site = site_name[0] if isinstance(site_name, list) else site_name
            if site == "glassdoor":
                glassdoor_calls.append(1)
                raise Exception("Glassdoor response status code 403")
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch(
            "job_hunter_core.sources.jobspy_source.load_api_config", return_value=_GLASSDOOR_CFG
        ):
            JobSpySource().fetch(
                ["Product Manager", "Senior PM"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert "glassdoor" in jspy_mod._DISABLED_SITES
        # Disabled after the first call — should not have been called a second time
        assert len(glassdoor_calls) == 1

    def test_non_403_does_not_disable_site(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        def fake_scrape(site_name, **kw):
            raise Exception("Connection timeout after 10s")

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch(
            "job_hunter_core.sources.jobspy_source.load_api_config", return_value=_GLASSDOOR_CFG
        ):
            JobSpySource().fetch(
                ["Product Manager"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        # Timeout is not a 403 — site must not be permanently disabled
        assert "google" not in jspy_mod._DISABLED_SITES
        assert "glassdoor" not in jspy_mod._DISABLED_SITES

    def test_forbidden_string_also_disables_site(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        def fake_scrape(site_name, **kw):
            site = site_name[0] if isinstance(site_name, list) else site_name
            if site == "indeed":
                raise Exception("403 Client Error: Forbidden for url: https://indeed.com")
            return None

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
        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=cfg):
            JobSpySource().fetch(
                ["Product Manager"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert "indeed" in jspy_mod._DISABLED_SITES

    def test_all_sites_disabled_skips_remaining_titles(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        # Pre-disable all sites to confirm nothing is called
        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", {"google", "indeed", "glassdoor"})

        call_count = []

        def fake_scrape(**kw):
            call_count.append(1)
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch(
            "job_hunter_core.sources.jobspy_source.load_api_config", return_value=_GLASSDOOR_CFG
        ):
            jobs = JobSpySource().fetch(
                ["Product Manager", "Senior PM"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert jobs == []
        assert call_count == []
