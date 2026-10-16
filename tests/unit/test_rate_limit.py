"""Unit tests for the in-memory RateLimiter (Step 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wbms.web.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_allows_up_to_the_limit_then_blocks():
    limiter = RateLimiter(5, 60, FakeClock())

    results = [limiter.hit("1.2.3.4").allowed for _ in range(6)]

    assert results == [True, True, True, True, True, False]


def test_blocked_decision_says_how_long_to_wait():
    clock = FakeClock()
    limiter = RateLimiter(2, 60, clock)
    limiter.hit("ip")
    clock.advance(10)
    limiter.hit("ip")

    decision = limiter.hit("ip")

    assert decision.allowed is False
    assert decision.retry_after_s == 50


def test_allows_again_exactly_when_the_window_has_passed():
    clock = FakeClock()
    limiter = RateLimiter(1, 60, clock)
    limiter.hit("ip")

    clock.advance(59)
    assert limiter.hit("ip").allowed is False
    clock.advance(1)
    assert limiter.hit("ip").allowed is True


def test_each_key_has_its_own_budget():
    limiter = RateLimiter(1, 60, FakeClock())

    assert limiter.hit("a").allowed is True
    assert limiter.hit("b").allowed is True
    assert limiter.hit("a").allowed is False


def test_rejected_requests_do_not_extend_the_wait():
    clock = FakeClock()
    limiter = RateLimiter(1, 60, clock)
    limiter.hit("ip")
    for _ in range(10):
        clock.advance(5)
        limiter.hit("ip")

    clock.advance(10)

    assert limiter.hit("ip").allowed is True


def test_expired_keys_are_purged_when_too_many_keys_are_tracked():
    clock = FakeClock()
    limiter = RateLimiter(1, 60, clock, max_keys=3)
    for i in range(4):
        limiter.hit(f"ip{i}")
    clock.advance(61)

    limiter.hit("fresh")

    assert set(limiter._hits) == {"fresh"}


@pytest.mark.parametrize("limit,window", [(0, 60), (5, 0), (-1, 60)])
def test_invalid_settings_are_rejected(limit, window):
    with pytest.raises(ValueError):
        RateLimiter(limit, window)
