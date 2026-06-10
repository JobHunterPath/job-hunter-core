from __future__ import annotations

import pytest

from job_hunter_core.sources.base import JobSourceAdapter


def test_cannot_instantiate_abstract():
    with pytest.raises(TypeError):
        JobSourceAdapter()  # type: ignore[abstract]


def test_concrete_subclass_instantiates():
    class MySource(JobSourceAdapter):
        @property
        def name(self) -> str:
            return "my_source"

        def fetch(self, title_filters, location_filter, config, *, excluded_title_terms=None):
            return []

    src = MySource()
    assert src.name == "my_source"
    assert src.fetch([], "", {}) == []


def test_is_enabled_defaults_true():
    class AnotherSource(JobSourceAdapter):
        @property
        def name(self) -> str:
            return "another"

        def fetch(self, title_filters, location_filter, config, *, excluded_title_terms=None):
            return []

    src = AnotherSource()
    assert src.is_enabled({}) is True
    assert src.is_enabled({"some_key": "some_val"}) is True
