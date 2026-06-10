#!/usr/bin/env python3
"""Validate a JobSourceAdapter subclass contract."""
import importlib
import sys


def validate(dotted: str) -> None:
    module_path, cls_name = dotted.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)

    from job_hunter_core.sources.base import JobSourceAdapter

    assert issubclass(cls, JobSourceAdapter), f"{cls_name} does not subclass JobSourceAdapter"

    inst = cls()
    assert isinstance(inst.name, str) and inst.name, "name property must return a non-empty string"

    result = inst.fetch(["Engineer"], "", {})
    assert isinstance(result, list), "fetch() must return a list"
    print(f"OK: {cls_name} passes adapter contract checks")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: validate_adapter.py <module.ClassName>")
        sys.exit(1)
    validate(sys.argv[1])
