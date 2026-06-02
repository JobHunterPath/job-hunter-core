from pathlib import Path

import yaml

from job_hunter_core.discovery import discoverer


def _write_search_config(path: Path, regions: dict, discovery: dict | None = None) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "regions": regions,
                "global_search": {"job_titles": ["Product Manager"]},
                "exclusion_rules": {"excluded_industries": []},
                "discovery": {
                    "max_workers": 2,
                    "total_timeout_seconds": 1800,
                    "reserve_seconds": 600,
                    "overlap_scope": "new_only",
                    "sectors": ["saas"],
                    **(discovery or {}),
                },
                "excluded_companies": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _read_search_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_discovery_settings_use_defaults_when_keys_are_absent():
    settings = discoverer._discovery_settings({"discovery": {}})

    assert settings == {
        "max_workers": 10,
        "total_timeout_seconds": 1800,
        "reserve_seconds": 600,
        "overlap_scope": "new_only",
    }


def test_run_parallel_until_deadline_collects_worker_results():
    deadline = discoverer.time.monotonic() + 30

    results, timed_out = discoverer._run_parallel_until_deadline(
        ["alpha", "beta"],
        lambda item: item.upper(),
        max_workers=2,
        deadline=deadline,
        label="test work",
    )

    assert sorted(results) == ["ALPHA", "BETA"]
    assert timed_out is False


def test_career_url_lookups_add_returned_companies(monkeypatch, tmp_path):
    cfg = tmp_path / "search_config.yml"
    _write_search_config(
        cfg,
        {
            "berlin": {
                "enabled": True,
                "location": "Berlin",
                "companies": [],
            }
        },
    )
    monkeypatch.setattr(discoverer, "SEARCH_CONFIG_FILE", str(cfg))
    monkeypatch.setattr(discoverer, "discover_company_names", lambda *args: ["BetaCo", "AlphaCo"])
    monkeypatch.setattr(
        discoverer,
        "discover_company_candidates",
        lambda *args: [{"name": "GammaCo", "career_url": "jobs.lever.co/gammaco"}],
    )
    monkeypatch.setattr(discoverer, "has_jobs_in_location", lambda *args: False)

    def fake_find(name, existing_urls, region_config):
        return {"name": name, "career_url": f"jobs.lever.co/{name.lower()}"}

    monkeypatch.setattr(discoverer, "find_career_url", fake_find)

    discoverer.run()

    companies = _read_search_config(cfg)["regions"]["berlin"]["companies"]
    assert companies == [
        {"name": "AlphaCo", "career_url": "jobs.lever.co/alphaco"},
        {"name": "BetaCo", "career_url": "jobs.lever.co/betaco"},
        {"name": "GammaCo", "career_url": "jobs.lever.co/gammaco"},
    ]


def test_deadline_during_lookup_saves_partial_results_and_stops(monkeypatch, tmp_path):
    cfg = tmp_path / "search_config.yml"
    _write_search_config(
        cfg,
        {
            "berlin": {
                "enabled": True,
                "location": "Berlin",
                "companies": [],
            },
            "dublin": {
                "enabled": True,
                "location": "Dublin",
                "companies": [],
            },
        },
    )
    monkeypatch.setattr(discoverer, "SEARCH_CONFIG_FILE", str(cfg))
    calls = []
    monkeypatch.setattr(discoverer, "discover_company_names", lambda *args: ["PartialCo"])
    monkeypatch.setattr(discoverer, "discover_company_candidates", lambda *args: [])

    def fake_parallel(items, worker, max_workers, deadline, label):
        calls.append(label)
        return [{"name": "PartialCo", "career_url": "jobs.lever.co/partialco"}], True

    monkeypatch.setattr(discoverer, "_run_parallel_until_deadline", fake_parallel)

    discoverer.run()

    saved = _read_search_config(cfg)
    assert saved["regions"]["berlin"]["companies"] == [
        {"name": "PartialCo", "career_url": "jobs.lever.co/partialco"}
    ]
    assert saved["regions"]["dublin"]["companies"] == []
    assert calls == ["career URL lookup for berlin"]


def test_overlap_checks_only_newly_discovered_companies(monkeypatch, tmp_path):
    cfg = tmp_path / "search_config.yml"
    _write_search_config(
        cfg,
        {
            "berlin": {
                "enabled": True,
                "location": "Berlin",
                "companies": [{"name": "OldCo", "career_url": "jobs.lever.co/oldco"}],
            },
            "remote_germany": {
                "enabled": True,
                "location": "remote Germany",
                "companies": [],
            },
        },
    )
    monkeypatch.setattr(discoverer, "SEARCH_CONFIG_FILE", str(cfg))

    def fake_suggestions(existing, location, job_titles, sectors, excluded_industries):
        return ["NewCo"] if location == "Berlin" else []

    checked = []
    monkeypatch.setattr(discoverer, "discover_company_names", fake_suggestions)
    monkeypatch.setattr(discoverer, "discover_company_candidates", lambda *args: [])
    monkeypatch.setattr(
        discoverer,
        "find_career_url",
        lambda name, existing_urls, region_config: {
            "name": name,
            "career_url": f"jobs.lever.co/{name.lower()}",
        },
    )

    def fake_has_jobs(company_name, region_config):
        checked.append(company_name)
        return True

    monkeypatch.setattr(discoverer, "has_jobs_in_location", fake_has_jobs)

    discoverer.run()

    saved = _read_search_config(cfg)
    remote_names = [company["name"] for company in saved["regions"]["remote_germany"]["companies"]]
    assert checked == ["NewCo"]
    assert remote_names == ["NewCo"]
    assert "OldCo" not in checked


def test_ats_discovery_runs_without_llm_sectors(monkeypatch, tmp_path):
    cfg = tmp_path / "search_config.yml"
    _write_search_config(
        cfg,
        {
            "berlin": {
                "enabled": True,
                "location": "Berlin",
                "companies": [],
            }
        },
        discovery={"sectors": []},
    )
    monkeypatch.setattr(discoverer, "SEARCH_CONFIG_FILE", str(cfg))
    monkeypatch.setattr(discoverer, "discover_company_names", lambda *args: [])
    monkeypatch.setattr(
        discoverer,
        "discover_company_candidates",
        lambda *args: [{"name": "SearchCo", "career_url": "jobs.ashbyhq.com/searchco"}],
    )
    monkeypatch.setattr(discoverer, "has_jobs_in_location", lambda *args: False)

    discoverer.run()

    companies = _read_search_config(cfg)["regions"]["berlin"]["companies"]
    assert companies == [{"name": "SearchCo", "career_url": "jobs.ashbyhq.com/searchco"}]
