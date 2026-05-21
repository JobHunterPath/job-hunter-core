"""Smoke tests for YAML files touched by automation changes."""

from pathlib import Path
import subprocess

import yaml


def test_workflow_and_config_yaml_parse():
    files = [
        ".github/workflows/daily_jobs.yml",
        "config/search_config.yml",
        "config/api_config.yml",
        "config/discovery_cache.yml",
        "template/config/search_config.yml",
        "template/config/api_config.yml",
        "template/config/discovery_cache.yml",
    ]

    for file in files:
        yaml.safe_load(Path(file).read_text(encoding="utf-8"))


def test_daily_hunt_crons_match_enabled_regions_with_companies():
    config = yaml.safe_load(Path("config/search_config.yml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load(Path(".github/workflows/daily_jobs.yml").read_text(encoding="utf-8"))

    regions = [
        name
        for name, region in (config.get("regions") or {}).items()
        if region.get("enabled", True) and region.get("companies")
    ]
    hunt_crons = [
        item["cron"]
        for item in workflow[True]["schedule"]
        if item["cron"] != "0 18 * * 1"
    ]
    resolve_step = next(
        step
        for step in workflow["jobs"]["hunt"]["steps"]
        if step.get("id") == "hunt_region"
    )
    configured_schedules = [
        line.strip()
        for line in resolve_step["env"]["HUNT_SCHEDULES"].splitlines()
        if line.strip()
    ]

    assert len(hunt_crons) == len(regions)
    assert hunt_crons == configured_schedules


def test_template_profile_files_are_present_or_optional():
    template_cfg = yaml.safe_load(
        Path("template/config/api_config.yml").read_text(encoding="utf-8")
    )
    profile = template_cfg["profile"]
    for key in ("resume_tex", "story_bank", "project_instructions"):
        assert (Path("template") / profile[key]).exists(), key
    assert Path(profile["latex_class"]).exists()

    profile_image = profile.get("profile_image", "")
    assert not profile_image or (Path("template") / profile_image).exists()


def _shape(value, path=""):
    if isinstance(value, dict):
        if path == "regions" or path.endswith(".regions") or path.endswith("_by_region"):
            if not value:
                return {}
            item_shapes = [_shape(item, f"{path}.*") for item in value.values()]
            return {"*": _merge_shapes(item_shapes)}
        return {
            key: _shape(item, f"{path}.{key}" if path else str(key))
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        if not value:
            return []
        return [_merge_shapes([_shape(item, f"{path}[]") for item in value])]
    return type(value).__name__


def _merge_shapes(shapes):
    merged = {}
    for shape in shapes:
        if isinstance(shape, dict):
            for key, value in shape.items():
                if key not in merged:
                    merged[key] = value
                elif merged[key] != value:
                    merged[key] = _merge_shapes([merged[key], value])
        else:
            return shape
    return merged


def test_live_template_config_shapes_match():
    pairs = [
        ("config/api_config.yml", "template/config/api_config.yml"),
        ("config/search_config.yml", "template/config/search_config.yml"),
        ("config/scoring_config.yml", "template/config/scoring_config.yml"),
        ("config/tailoring_config.yml", "template/config/tailoring_config.yml"),
        ("config/cover_letter_config.yml", "template/config/cover_letter_config.yml"),
    ]

    for live_path, template_path in pairs:
        live = yaml.safe_load(Path(live_path).read_text(encoding="utf-8")) or {}
        template = yaml.safe_load(Path(template_path).read_text(encoding="utf-8")) or {}
        assert _shape(live) == _shape(template), f"{live_path} drifted from {template_path}"


def test_workflows_do_not_use_broad_git_add():
    for path in Path(".github/workflows").glob("*.yml"):
        content = path.read_text(encoding="utf-8")
        assert "git add -A" not in content
        assert "git add ." not in content
        assert "git add jobs/" not in content


def test_generated_job_profile_images_are_ignored():
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "jobs/example/Profile-2025.png"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
