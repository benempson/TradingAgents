"""YFRateLimiter — rolling-window rate limiter for yfinance API calls.

Enforces three rolling windows (per-minute, per-hour, per-day) to stay within
safe yfinance request limits.  Window state is persisted to a JSON counter file
so counts survive process restarts within the same window.

Usage::

    from screener.yf_rate_limiter import YFRateLimiter, YFRateLimitExceeded

    limiter = YFRateLimiter()
    try:
        limiter.check_and_increment()
    except YFRateLimitExceeded as exc:
        logger.error("Rate limit reached: %s", exc)
        raise SystemExit(1)
    # ... safe to call yfinance here ...
"""

import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_LIMIT_PER_MIN: int = 100
_DEFAULT_LIMIT_PER_HOUR: int = 2000
_DEFAULT_LIMIT_PER_DAY: int = 48000
_DEFAULT_COUNTER_FILE: str = "temp/screener/yf_rate_counters.json"

# Map window name → timedelta duration
_WINDOW_DURATIONS: dict[str, datetime.timedelta] = {
    "minute": datetime.timedelta(minutes=1),
    "hour": datetime.timedelta(hours=1),
    "day": datetime.timedelta(days=1),
}


# ── custom exception ──────────────────────────────────────────────────────────


class YFRateLimitExceeded(Exception):
    """Raised when a rolling-window yfinance rate limit has been reached.

    Args:
        window: Name of the exhausted window (``"minute"``, ``"hour"``, or ``"day"``).
        count: Current request count in this window.
        limit: Maximum allowed requests in this window.
        reset_at: UTC datetime when this window resets.
    """

    def __init__(
        self,
        window: str,
        count: int,
        limit: int,
        reset_at: datetime.datetime,
    ) -> None:
        self.window = window
        self.count = count
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(
            f"yfinance {window} limit reached ({count}/{limit}). "
            f"Retry after {reset_at.isoformat()}."
        )


# ── main class ────────────────────────────────────────────────────────────────


class YFRateLimiter:
    """Rolling-window rate limiter for yfinance API calls.

    Reads limits from environment variables on instantiation and persists
    window state to disk so counts are accurate across process restarts.

    Environment variables:
        YF_LIMIT_PER_MIN:      Per-minute request ceiling (default 100).
        YF_LIMIT_PER_HOUR:     Per-hour request ceiling (default 2000).
        YF_LIMIT_PER_DAY:      Per-day request ceiling (default 48000).
        YF_RATE_COUNTER_FILE:  Path to the JSON state file.

    Args:
        counter_file: Explicit path to the JSON counter file.  If ``None``,
            falls back to ``YF_RATE_COUNTER_FILE`` env var or the built-in
            default (``temp/screener/yf_rate_counters.json``).
    """

    def __init__(self, counter_file: str | None = None) -> None:
        self._counter_file: str = counter_file or os.environ.get(
            "YF_RATE_COUNTER_FILE", _DEFAULT_COUNTER_FILE
        )

        # Load limits from env vars, falling back to hard-coded defaults.
        self._limits: dict[str, int] = {
            "minute": int(
                os.environ.get("YF_LIMIT_PER_MIN", _DEFAULT_LIMIT_PER_MIN)
            ),
            "hour": int(
                os.environ.get("YF_LIMIT_PER_HOUR", _DEFAULT_LIMIT_PER_HOUR)
            ),
            "day": int(
                os.environ.get("YF_LIMIT_PER_DAY", _DEFAULT_LIMIT_PER_DAY)
            ),
        }

        logger.info(
            "YFRateLimiter initialised",
            extra={
                "counter_file": self._counter_file,
                "limits": self._limits,
            },
        )

        self._state: dict[str, dict] = self._load_state()

    # ── public API ────────────────────────────────────────────────────────────

    def check_and_increment(self) -> None:
        """Check all rolling windows; raise if any limit is reached.

        Checks all three windows *before* incrementing any counter.  If any
        window has already reached its limit, raises ``YFRateLimitExceeded``
        immediately without modifying state.

        Otherwise increments all counters and persists state to disk.

        Raises:
            YFRateLimitExceeded: When any window is at its limit.
        """
        logger.info("check_and_increment called")

        now = datetime.datetime.now(datetime.timezone.utc)

        # Reset expired windows first so fresh windows aren't blocked.
        self._reset_expired_windows(now)

        # Validate ALL windows before touching any counter (atomic check).
        for window in ("minute", "hour", "day"):
            count = self._state[window]["count"]
            limit = self._limits[window]
            if count >= limit:
                reset_at = self._state[window]["window_start"] + _WINDOW_DURATIONS[window]
                logger.warning(
                    "yfinance rate limit reached",
                    extra={
                        "window": window,
                        "count": count,
                        "limit": limit,
                        "reset_at": reset_at.isoformat(),
                    },
                )
                raise YFRateLimitExceeded(
                    window=window,
                    count=count,
                    limit=limit,
                    reset_at=reset_at,
                )

        # All windows are within limits — increment all counters.
        for window in ("minute", "hour", "day"):
            self._state[window]["count"] += 1

        logger.info(
            "Counters incremented",
            extra={
                w: self._state[w]["count"] for w in ("minute", "hour", "day")
            },
        )

        self._save_state()

    # ── internals ─────────────────────────────────────────────────────────────

    def _reset_expired_windows(self, now: datetime.datetime) -> None:
        """Reset any window whose duration has elapsed since its window_start.

        Args:
            now: Current UTC datetime.
        """
        for window, duration in _WINDOW_DURATIONS.items():
            window_start = self._state[window]["window_start"]
            if now - window_start >= duration:
                logger.info(
                    "Resetting expired window",
                    extra={"window": window, "old_start": window_start.isoformat()},
                )
                self._state[window] = {"count": 0, "window_start": now}

    def _load_state(self) -> dict[str, dict]:
        """Load window state from the counter file.

        If the file does not exist or contains corrupt JSON, fresh state is
        returned (all windows at count=0).

        Returns:
            Dict with keys ``"minute"``, ``"hour"``, ``"day"``, each containing
            ``{"count": int, "window_start": datetime}``.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        fresh_state = self._fresh_state(now)

        if not os.path.exists(self._counter_file):
            logger.info(
                "Counter file not found; starting with fresh state",
                extra={"counter_file": self._counter_file},
            )
            return fresh_state

        try:
            with open(self._counter_file, "r", encoding="utf-8") as fh:
                raw: dict = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Counter file corrupt or unreadable; starting with fresh state",
                extra={"counter_file": self._counter_file, "error": str(exc)},
            )
            return fresh_state

        # Parse the raw JSON into typed state, falling back to fresh per-window.
        state: dict[str, dict] = {}
        for window in ("minute", "hour", "day"):
            if window not in raw:
                state[window] = {"count": 0, "window_start": now}
                continue
            try:
                count = int(raw[window]["count"])
                window_start = datetime.datetime.fromisoformat(
                    raw[window]["window_start"]
                )
                # Ensure timezone-aware.
                if window_start.tzinfo is None:
                    window_start = window_start.replace(
                        tzinfo=datetime.timezone.utc
                    )
                state[window] = {"count": count, "window_start": window_start}
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Corrupt window entry; resetting to fresh state",
                    extra={"window": window, "error": str(exc)},
                )
                state[window] = {"count": 0, "window_start": now}

        logger.info(
            "Loaded counter state from disk",
            extra={
                w: state[w]["count"] for w in ("minute", "hour", "day")
            },
        )
        return state

    def _save_state(self) -> None:
        """Persist current window state to the counter file atomically.

        Writes to a ``.tmp`` file then uses ``os.replace()`` so that a partial
        write never leaves a corrupt state file.  Logs a warning on
        ``PermissionError`` but does not raise.
        """
        serialisable = {
            window: {
                "count": data["count"],
                "window_start": data["window_start"].isoformat(),
            }
            for window, data in self._state.items()
        }

        tmp_path = self._counter_file + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._counter_file) or ".", exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(serialisable, fh, indent=2)
            os.replace(tmp_path, self._counter_file)
        except PermissionError as exc:
            logger.warning(
                "Failed to persist rate counter state",
                extra={"counter_file": self._counter_file, "error": str(exc)},
            )
        except OSError as exc:
            logger.warning(
                "Failed to persist rate counter state",
                extra={"counter_file": self._counter_file, "error": str(exc)},
            )

    @staticmethod
    def _fresh_state(now: datetime.datetime) -> dict[str, dict]:
        """Return a fresh (zero-count) state dict for all windows.

        Args:
            now: UTC datetime to use as the ``window_start`` for each window.

        Returns:
            Dict keyed by window name with ``count=0`` and ``window_start=now``.
        """
        return {window: {"count": 0, "window_start": now} for window in _WINDOW_DURATIONS}
