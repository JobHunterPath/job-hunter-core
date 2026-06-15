"""Smoke tests for YAML files touched by automation changes."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml


def test_workflow_and_config_yaml_parse():
    files = [
        ".github/workflows/preflight_publish.yml",
    ]

    for file in files:
        path = Path(file)
        if path.exists():
            yaml.safe_load(path.read_text(encoding="utf-8"))


def test_private_template_yaml_files_parse_when_present():
    files = [
        ".github/workflows/job_hunt.yml",
        ".github/workflows/linkedin_content.yml",
        ".github/workflows/tailor_links.yml",
        ".github/workflows/tailor_raw.yml",
        ".github/workflows/update_from_template.yml",
        ".github/searxng/settings.yml",
        "config/search_config.yml",
        "config/api_config.yml",
        "config/discovery_cache.yml",
        "config/templates/search_config.yml",
        "config/templates/api_config.yml",
        "config/templates/discovery_cache.yml",
        ".github/template-workflows/job_hunt.yml",
        ".github/template-workflows/update_from_template.yml",
    ]

    for file in files:
        path = Path(file)
        if path.exists():
            yaml.safe_load(path.read_text(encoding="utf-8"))


def test_template_job_hunt_passes_job_board_api_keys_to_container():
    path = Path(".github/template-workflows/job_hunt.yml")
    if not path.exists():
        return

    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["hunt"]["steps"]
    named_steps = {step.get("name"): step for step in steps}

    for name in ("Scrape jobs", "Tailor jobs"):
        step = named_steps[name]
        env = step.get("env") or {}
        run = step.get("run") or ""
        assert env["JOOBLE_API_KEY"] == "${{ secrets.JOOBLE_API_KEY }}"
        assert env["FIRECRAWL_API_KEY"] == "${{ secrets.FIRECRAWL_API_KEY }}"
        assert "-e JOOBLE_API_KEY" in run
        assert "-e FIRECRAWL_API_KEY" in run


def test_search_schema_rejects_region_companies() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path("config/schemas/search_config.schema.json")
    if not schema_path.exists():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    bad = {
        "regions": {
            "primary": {
                "enabled": True,
                "country": "DE",
                "companies": [{"name": "Acme"}],
            }
        },
        "global_search": {"job_titles": []},
        "exclusion_rules": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_search_schema_rejects_top_level_scraping() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path("config/schemas/search_config.schema.json")
    if not schema_path.exists():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    bad = {
        "regions": {},
        "global_search": {"job_titles": []},
        "exclusion_rules": {},
        "scraping": {"total_timeout_seconds": 120},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_search_schema_rejects_top_level_ats_discovery() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path("config/schemas/search_config.schema.json")
    if not schema_path.exists():
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    bad = {
        "regions": {},
        "global_search": {"job_titles": []},
        "exclusion_rules": {},
        "ats_discovery": {"enabled": True},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_template_profile_files_are_present_or_optional():
    if not Path("config/templates/api_config.yml").exists():
        return

    template_cfg = yaml.safe_load(
        Path("config/templates/api_config.yml").read_text(encoding="utf-8")
    )
    profile = template_cfg["profile"]
    profile_root = Path("profile/template-files")
    for key in ("resume_tex", "story_bank"):
        assert (profile_root / profile[key]).exists(), key
    assert (profile_root / profile["latex_class"]).exists()

    profile_image = profile.get("profile_image", "")
    assert not profile_image or (profile_root / profile_image).exists()


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
        ("config/api_config.yml", "config/templates/api_config.yml"),
        ("config/search_config.yml", "config/templates/search_config.yml"),
        ("config/scoring_config.yml", "config/templates/scoring_config.yml"),
        ("config/tailoring_config.yml", "config/templates/tailoring_config.yml"),
        ("config/cover_letter_config.yml", "config/templates/cover_letter_config.yml"),
    ]

    for live_path, template_path in pairs:
        if not Path(live_path).exists() or not Path(template_path).exists():
            continue

        live = yaml.safe_load(Path(live_path).read_text(encoding="utf-8")) or {}
        template = yaml.safe_load(Path(template_path).read_text(encoding="utf-8")) or {}
        assert _shape(live) == _shape(template), f"{live_path} drifted from {template_path}"


_REPO_ROOT = Path(__file__).parent.parent


def test_workflows_do_not_use_broad_git_add():
    paths = list((_REPO_ROOT / ".github/workflows").glob("*.yml"))
    paths.extend((_REPO_ROOT / ".github/template-workflows").glob("*.yml"))
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "git add -A" not in content
        assert "git add ." not in content
        assert "git add jobs/" not in content


def _workflow_step(workflow_path: str, job_name: str, step_name: str) -> dict:
    workflow = yaml.safe_load((_REPO_ROOT / workflow_path).read_text(encoding="utf-8"))
    steps = workflow["jobs"][job_name]["steps"]
    return next(step for step in steps if step.get("name") == step_name)


def test_preflight_publish_jobs_require_lint_and_tests():
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github/workflows/preflight_publish.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    assert jobs["release"]["needs"] == ["lint", "test"]
    assert jobs["sync-template"]["needs"] == ["lint", "test"]
    assert jobs["build-runner-image"]["needs"] == ["lint", "test"]


def test_preflight_publish_jobs_skip_release_maintenance_commits():
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github/workflows/preflight_publish.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    for job_name in ("release", "sync-template", "build-runner-image"):
        condition = jobs[job_name]["if"]
        assert "!startsWith(github.event.head_commit.message, 'chore(release):')" in condition
        assert "!startsWith(github.event.head_commit.message, 'chore: bump version')" in condition


def test_release_workflow_creates_core_release_and_announcements():
    step = _workflow_step(
        ".github/workflows/preflight_publish.yml",
        "release",
        "Create release",
    )
    run = step["run"]

    assert step["if"] == "steps.version.outputs.should_release == 'true'"
    assert 'gh release create "v${{ steps.version.outputs.new }}"' in run
    assert "--generate-notes" in run
    assert "--target main" in run

    discussion_step = _workflow_step(
        ".github/workflows/preflight_publish.yml",
        "release",
        "Post Discussion announcement",
    )
    discussion_run = discussion_step["run"]

    assert discussion_step["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert "Update From Template" in discussion_run
    assert "createDiscussion(input:" in discussion_run


def test_release_workflow_can_announce_to_template_repo():
    step = _workflow_step(
        ".github/workflows/preflight_publish.yml",
        "release",
        "Post cross-repo announcement to job-hunter-template",
    )
    run = step["run"]

    assert step["if"] == "steps.version.outputs.should_release == 'true'"
    assert step["env"]["GH_TOKEN"] == "${{ secrets.TEMPLATE_REPO_PAT }}"
    assert '-f owner="JobHunterPath"' in run
    assert '-f name="job-hunter-template"' in run
    assert "createDiscussion(input:" in run
    assert "https://github.com/JobHunterPath/job-hunter-core/releases/tag/$TAG" in run


def test_sync_template_workflow_assembles_template_repo_pr():
    step = _workflow_step(
        ".github/workflows/preflight_publish.yml",
        "sync-template",
        "Sync maintained template files",
    )
    assert step["run"] == "python .github/scripts/build_template_repo.py job-hunter-template"

    pr_step = _workflow_step(
        ".github/workflows/preflight_publish.yml",
        "sync-template",
        "Open PR in job-hunter-template",
    )
    assert pr_step["with"]["token"] == "${{ secrets.TEMPLATE_REPO_PAT }}"
    assert pr_step["with"]["path"] == "job-hunter-template"
    assert pr_step["with"]["commit-message"] == ("chore: sync template files from job-hunter-core")


def test_generated_job_latex_assets_are_trackable():
    if not Path(".git").exists() or not Path(".gitignore").exists():
        return

    for path in ("jobs/example/Profile-2025.png", "jobs/example/altacv.cls"):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", path],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
