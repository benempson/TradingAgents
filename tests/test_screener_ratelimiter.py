"""Tests for screener/yf_rate_limiter.py — YFRateLimiter.

Covers:
- Minute-window blocking on limit reached (R-RATE-04)
- Automatic window reset after window_duration has elapsed (R-RATE-05)
- State persistence across YFRateLimiter instances (R-RATE-03)
"""

import datetime
import json
import os

import pytest

from screener.yf_rate_limiter import YFRateLimitExceeded, YFRateLimiter

# ── helpers ───────────────────────────────────────────────────────────────────


def _write_state(path: str, state: dict) -> None:
    """Write a JSON state dict directly to the counter file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


# ── tests ─────────────────────────────────────────────────────────────────────


class TestRateLimiterMinuteBlock:
    """R-RATE-04: Second call within same window raises YFRateLimitExceeded."""

    def test_rate_limiter_blocks_on_minute_limit(
        self, tmp_path, monkeypatch
    ) -> None:
        counter_file = str(tmp_path / "yf_counters.json")

        # Limit per-minute to 1 so that the second call is blocked.
        monkeypatch.setenv("YF_LIMIT_PER_MIN", "1")
        # Use large limits for hour/day so only the minute window triggers.
        monkeypatch.setenv("YF_LIMIT_PER_HOUR", "10000")
        monkeypatch.setenv("YF_LIMIT_PER_DAY", "1000000")

        limiter = YFRateLimiter(counter_file=counter_file)

        # First call must succeed (count goes from 0 → 1, limit is 1).
        limiter.check_and_increment()

        # Second call must raise because count (1) == limit (1).
        with pytest.raises(YFRateLimitExceeded) as exc_info:
            limiter.check_and_increment()

        exc = exc_info.value
        assert exc.window == "minute"
        assert exc.count == 1
        assert exc.limit == 1
        assert isinstance(exc.reset_at, datetime.datetime)
        assert exc.reset_at.tzinfo is not None  # must be timezone-aware


class TestRateLimiterWindowReset:
    """R-RATE-05: Window resets automatically when window_duration has elapsed."""

    def test_rate_limiter_resets_after_window(
        self, tmp_path, monkeypatch
    ) -> None:
        counter_file = str(tmp_path / "yf_counters.json")

        # Give a tight per-minute limit; counts in stale window should not matter.
        monkeypatch.setenv("YF_LIMIT_PER_MIN", "1")
        monkeypatch.setenv("YF_LIMIT_PER_HOUR", "10000")
        monkeypatch.setenv("YF_LIMIT_PER_DAY", "1000000")

        # Inject a stale state file: minute window started >61 s ago with count=1
        # (i.e., at the limit).  After reset the count becomes 0 so the call must
        # succeed.
        stale_start = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=61)
        ).isoformat()

        _write_state(
            counter_file,
            {
                "minute": {"count": 1, "window_start": stale_start},
                "hour": {"count": 1, "window_start": stale_start},
                "day": {"count": 1, "window_start": stale_start},
            },
        )

        limiter = YFRateLimiter(counter_file=counter_file)

        # Must not raise — the stale minute window should have been reset to 0.
        limiter.check_and_increment()


class TestRateLimiterPersistence:
    """R-RATE-03: Counter state is loaded from disk on new instantiation."""

    def test_rate_limiter_persists_across_runs(
        self, tmp_path, monkeypatch
    ) -> None:
        counter_file = str(tmp_path / "yf_counters.json")

        monkeypatch.setenv("YF_LIMIT_PER_MIN", "100")
        monkeypatch.setenv("YF_LIMIT_PER_HOUR", "10000")
        monkeypatch.setenv("YF_LIMIT_PER_DAY", "1000000")

        # First instance: call check_and_increment three times.
        limiter_a = YFRateLimiter(counter_file=counter_file)
        limiter_a.check_and_increment()
        limiter_a.check_and_increment()
        limiter_a.check_and_increment()

        # Verify the state file was written with count=3 for minute window.
        with open(counter_file, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        assert saved["minute"]["count"] == 3

        # Second instance: loads the persisted count of 3, then increments to 4.
        limiter_b = YFRateLimiter(counter_file=counter_file)
        limiter_b.check_and_increment()

        with open(counter_file, "r", encoding="utf-8") as fh:
            updated = json.load(fh)
        assert updated["minute"]["count"] == 4
