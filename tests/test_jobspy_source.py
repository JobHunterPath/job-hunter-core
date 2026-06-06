from types import SimpleNamespace
from unittest.mock import patch

from job_hunter_core.sources.jobspy_source import fetch_jobspy_jobs

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
