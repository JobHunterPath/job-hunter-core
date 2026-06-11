from types import SimpleNamespace
from unittest.mock import patch

from job_hunter_core.sources.jobspy_source import JobSpySource

_BASE_CFG = {
    "http": {
        "job_boards": {
            "jobspy": {
                "enabled": True,
                "results_per_query": 5,
                "hours_old": 72,
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
            "location": "Berlin, DE",
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

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            jobs = JobSpySource().fetch(
                ["Software Engineer"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {"exclusion_rules": {"excluded_title_terms": []}},
            )
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobSpy/Google"
        assert jobs[0].location == "Berlin, DE"


class TestJobSpyCircuitBreaker:
    def test_403_disables_site_after_first_failure(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        indeed_calls = []

        def fake_scrape(site_name, **kw):
            site = site_name[0] if isinstance(site_name, list) else site_name
            if site == "indeed":
                indeed_calls.append(1)
                raise Exception("Indeed response status code 403")
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(
                ["Product Manager", "Senior PM"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert "indeed" in jspy_mod._DISABLED_SITES
        # Disabled after the first call — should not have been called a second time
        assert len(indeed_calls) == 1

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

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(
                ["Product Manager"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert "google" not in jspy_mod._DISABLED_SITES
        assert "indeed" not in jspy_mod._DISABLED_SITES

    def test_forbidden_string_also_disables_site(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        def fake_scrape(site_name, **kw):
            site = site_name[0] if isinstance(site_name, list) else site_name
            if site == "indeed":
                raise Exception("403 Client Error: Forbidden for url: https://indeed.com")
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(
                ["Product Manager"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert "indeed" in jspy_mod._DISABLED_SITES

    def test_all_sites_disabled_skips_remaining_titles(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        # Pre-disable all auto-selected sites (google + indeed for DE region)
        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", {"google", "indeed"})

        call_count = []

        def fake_scrape(**kw):
            call_count.append(1)
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            jobs = JobSpySource().fetch(
                ["Product Manager", "Senior PM"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert jobs == []
        assert call_count == []


class TestJobSpyAutoSelection:
    def test_google_and_indeed_selected_for_mapped_country(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        calls: list[str] = []

        def fake_scrape(site_name, **kw):
            calls.append(site_name[0])
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(
                ["Engineer"],
                {"DE": {"country": "DE", "location": "Berlin"}},
                {},
            )

        assert "google" in calls
        assert "indeed" in calls

    def test_only_google_for_unmapped_country(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        calls: list[str] = []

        def fake_scrape(site_name, **kw):
            calls.append(site_name[0])
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(
                ["Engineer"],
                # ZZ has no Indeed mapping
                {"ZZ": {"country": "ZZ", "location": "Somewhere"}},
                {},
            )

        assert "google" in calls
        assert "indeed" not in calls

    def test_google_search_term_passed_to_scrape(self, monkeypatch):
        import job_hunter_core.sources.jobspy_source as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        captured: list[dict] = []

        def fake_scrape(site_name, **kw):
            captured.append({"site": site_name[0], **kw})
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter_core.sources.jobspy_source.load_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(
                ["Data Scientist"],
                {"US": {"country": "US", "location": "Austin"}},
                {},
            )

        assert len(captured) >= 1
        for call in captured:
            assert call.get("google_search_term") == "Data Scientist"
            assert call.get("search_term") == "Data Scientist"
