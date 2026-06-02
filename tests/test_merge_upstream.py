import importlib.util
from pathlib import Path


def _load_merge_upstream_module():
    path = Path(__file__).parent.parent / ".github/scripts/merge_upstream.py"
    spec = importlib.util.spec_from_file_location("merge_upstream", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_upstream_preserves_readme_application_stats_and_table():
    merge_upstream = _load_merge_upstream_module()
    upstream = (Path(__file__).parent.parent / "README.template.md").read_text(encoding="utf-8")
    private = """
# My Job Hunt

## Applied Jobs

<!-- JOBS_STATS_START -->
**Application stats:** 2 jobs tracked since 2026-05-01 (3 weeks).
<!-- JOBS_STATS_END -->

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
| 2026-05-15 | [PM @ Example](https://example.com/job) | Berlin | 91 | [Files](jobs/example/) |
<!-- JOBS_TABLE_END -->
"""

    merged = merge_upstream.inject_sections(
        upstream,
        merge_upstream.extract_sections(private),
    )

    assert "No jobs tracked yet." not in merged
    assert "**Application stats:** 2 jobs tracked" in merged
    assert "[PM @ Example](https://example.com/job)" in merged


def test_merge_upstream_uses_template_sections_when_private_file_has_no_markers():
    merge_upstream = _load_merge_upstream_module()
    upstream = """
<!-- JOBS_STATS_START -->
No jobs tracked yet.
<!-- JOBS_STATS_END -->
"""

    merged = merge_upstream.inject_sections(upstream, {})

    assert "No jobs tracked yet." in merged
