from job_hunter_core.pipeline import resolve_hunt_region as resolver

SCHEDULES = [
    "0 4 * * 1-5",
    "0 5 * * 1,3,5",
    "0 6 * * 1,3,5",
]


def _config(regions):
    return {"regions": regions}


def test_scheduled_primary_slot_uses_primary_region():
    config = _config(
        {
            "berlin": {"enabled": True, "primary": True, "companies": [{"name": "A"}]},
            "oman": {"enabled": True, "companies": [{"name": "B"}]},
        }
    )

    status, outputs = resolver.resolve_hunt_region(
        config, "schedule", SCHEDULES[0], "all", SCHEDULES
    )

    assert status == 0
    assert outputs["should_run"] == "true"
    assert outputs["region"] == "berlin"
    assert outputs["arg"] == "--region berlin"


def test_scheduled_secondary_slots_follow_config_order():
    config = _config(
        {
            "berlin": {"enabled": True, "primary": True, "companies": [{"name": "A"}]},
            "malaysia": {"enabled": True, "companies": [{"name": "B"}]},
            "indonesia": {"enabled": True, "companies": [{"name": "C"}]},
        }
    )

    _, first_secondary = resolver.resolve_hunt_region(
        config, "schedule", SCHEDULES[1], "all", SCHEDULES
    )
    _, second_secondary = resolver.resolve_hunt_region(
        config, "schedule", SCHEDULES[2], "all", SCHEDULES
    )

    assert first_secondary["region"] == "malaysia"
    assert second_secondary["region"] == "indonesia"


def test_scheduled_empty_template_config_skips_cleanly():
    config = _config(
        {
            "primary": {"enabled": False, "primary": True, "companies": []},
        }
    )

    status, outputs = resolver.resolve_hunt_region(
        config, "schedule", SCHEDULES[0], "all", SCHEDULES
    )

    assert status == 0
    assert outputs["should_run"] == "false"
    assert "No enabled region" in outputs["reason"]


def test_manual_all_preserves_all_region_behavior():
    config = _config(
        {
            "berlin": {"enabled": True, "companies": [{"name": "A"}]},
        }
    )

    status, outputs = resolver.resolve_hunt_region(
        config, "workflow_dispatch", "", "all", SCHEDULES
    )

    assert status == 0
    assert outputs == {
        "should_run": "true",
        "region": "",
        "arg": "",
        "label": "all",
    }


def test_manual_unknown_region_errors_with_enabled_regions():
    config = _config(
        {
            "berlin": {"enabled": True, "companies": [{"name": "A"}]},
            "disabled": {"enabled": False, "companies": [{"name": "B"}]},
        }
    )

    status, outputs = resolver.resolve_hunt_region(
        config, "workflow_dispatch", "", "missing", SCHEDULES
    )

    assert status == 1
    assert "missing" in outputs["error"]
    enabled_list = outputs["error"].split("Enabled regions with companies: ", 1)[1]
    assert enabled_list == "berlin"
