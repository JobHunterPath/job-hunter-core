"""Per-run URL liveness cache."""

from __future__ import annotations

import threading
from collections.abc import Callable

from core.utils import url_is_alive

URLChecker = Callable[[str, int], bool]


class UrlLivenessCache:
    """Cache URL reachability verdicts for the current pipeline run."""

    def __init__(self, checker: URLChecker = url_is_alive) -> None:
        self._checker = checker
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, int], bool] = {}

    def is_alive(self, url: str, timeout: int) -> bool:
        key = (url, int(timeout))
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        result = self._checker(url, timeout)

        with self._lock:
            self._cache[key] = result
        return result
