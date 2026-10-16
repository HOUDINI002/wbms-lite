"""Small in-memory rate limiter (sliding window) with an injectable clock.

In-memory means the counters live inside one process: fine for the
prototype and one gunicorn worker; with several workers each keeps its own
count, so move this to Redis or the gateway/proxy when you scale.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Default clock: the current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of one ``hit``: allowed or not, and when to retry."""

    allowed: bool
    retry_after_s: int = 0


class RateLimiter:
    """Allow at most ``limit`` hits per ``window_seconds`` for each key."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Clock = utc_now,
        max_keys: int = 10_000,
    ) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be at least 1")
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> RateLimitDecision:
        """Record one request for ``key`` and say whether it is allowed.

        Rejected requests are not recorded, so hammering the endpoint does
        not extend the wait.
        """
        now = self._clock()
        with self._lock:
            if len(self._hits) > self._max_keys:
                self._purge(now)
            window = self._hits.setdefault(key, deque())
            while window and window[0] <= now - self._window:
                window.popleft()
            if len(window) >= self._limit:
                wait = (window[0] + self._window - now).total_seconds()
                return RateLimitDecision(False, max(1, math.ceil(wait)))
            window.append(now)
            return RateLimitDecision(True)

    def _purge(self, now: datetime) -> None:
        """Drop keys whose hits have all expired (keeps memory bounded)."""
        for key in [
            k for k, w in self._hits.items() if not w or w[-1] <= now - self._window
        ]:
            del self._hits[key]
