"""Lightweight runtime metrics logging helpers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging
    from collections.abc import Iterator


@contextmanager
def timed_stage(logger: logging.Logger, stage: str, **fields: object) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        extras = " ".join(f"{key}={value}" for key, value in fields.items())
        logger.info("[metrics] stage=%s duration_seconds=%.2f %s", stage, elapsed, extras)
