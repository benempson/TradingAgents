"""Tests for screener/screener.py — CLI orchestrator.

Covers:
  - Weekend date rollback logic (resolve_trade_date)
  - Invalid sector selection exits with code 1
  - main() with no_ta=True runs end-to-end without raising
  - _run_ta_for_ticker() marks failed propagation as ANALYSIS FAILED
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── Test 1: Saturday rolls back to Friday ─────────────────────────────────────


def test_weekend_date_rollback_saturday():
    from screener.screener import resolve_trade_date

    result = resolve_trade_date("2026-03-28")  # Saturday
    assert result == "2026-03-27"  # Friday


# ── Test 2: Sunday rolls back to Friday ───────────────────────────────────────


def test_weekend_date_rollback_sunday():
    from screener.screener import resolve_trade_date

    result = resolve_trade_date("2026-03-29")  # Sunday
    assert result == "2026-03-27"  # Friday


# ── Test 3: Weekday date is returned unchanged ────────────────────────────────


def test_weekday_date_unchanged():
    from screener.screener import resolve_trade_date

    result = resolve_trade_date("2026-03-27")  # Friday — no rollback
    assert result == "2026-03-27"


# ── Test 4: Invalid sector selection index exits with code 1 ──────────────────


def test_invalid_sector_selection_exits():
    from screener.screener import prompt_sector_selection

    sectors = [
        {
            "id": "tech",
            "name": "Technology",
            "etf": "XLK",
            "yf_sector": "Technology",
        }
    ]

    with patch("builtins.input", return_value="999"):
        with pytest.raises(SystemExit) as exc_info:
            prompt_sector_selection(sectors)
        assert exc_info.value.code == 1


# ── Test 5: main() with no_ta=True runs to completion without raising ─────────


def _make_sample_df() -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame sufficient for the indicator engine."""
    dates = pd.date_range("2025-01-01", periods=250, freq="B")
    n = len(dates)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * n,
            "High": [105.0] * n,
            "Low": [95.0] * n,
            "Close": [102.0] * n,
            "Volume": [1_000_000] * n,
        }
    )


def _make_minimal_config() -> dict:
    return {
        "sectors": [
            {
                "id": "tech",
                "name": "Technology",
                "etf": "XLK",
                "yf_sector": "Technology",
            }
        ],
        "discovery_criteria": [
            {
                "id": "momentum",
                "name": "Momentum",
                "description": "Test",
                "filters": [],
            }
        ],
        "screening_criteria": [
            {
                "id": "default",
                "name": "Default",
                "description": "Test",
                "hard_filters": {
                    "rsi": {"min": 40, "max": 70},
                    "volume": {"min_ratio": 1.2},
                    "atr_pct": {"min": 0.5, "max": 6.0},
                },
                "scoring": {"w1": 0.4, "w2": 0.4, "w3": 0.2},
            }
        ],
        "watchlists": [
            {
                "id": "tech",
                "name": "Tech",
                "description": "Test watchlist",
                "tickers": ["AAPL", "MSFT"],
            }
        ],
    }


def _make_sample_indicators(ticker: str) -> dict:
    """Return a valid indicators dict that will pass all hard filters."""
    return {
        "ticker": ticker,
        "close": 102.0,
        "sma_50": 98.0,
        "sma_200": 90.0,  # close > sma_200 → trend_filter passes
        "rsi": 55.0,  # within [40, 70]
        "macdh": 0.5,  # > 0 → macd_setup passes
        "macdh_crossed_up_3d": False,
        "macdh_series": [0.1, 0.3, 0.5],
        "vol_ratio": 1.5,  # >= 1.2 → volume passes
        "atr_pct": 2.0,  # within [0.5, 6.0]
        "atr": 2.04,
    }


def test_main_no_ta_runs_without_raising(capsys):
    """main() with no_ta=True completes the full pipeline without raising."""
    from screener.screener import main

    sample_df = _make_sample_df()
    minimal_config = _make_minimal_config()

    apply_results = [
        {
            "ticker": "AAPL",
            "score": 0.823,
            "indicators": _make_sample_indicators("AAPL"),
            "filter_results": {
                "trend_filter": True,
                "rsi_range": True,
                "macd_setup": True,
                "volume": True,
                "atr_pct": True,
            },
        },
        {
            "ticker": "MSFT",
            "score": 0.750,
            "indicators": _make_sample_indicators("MSFT"),
            "filter_results": {
                "trend_filter": True,
                "rsi_range": True,
                "macd_setup": True,
                "volume": True,
                "atr_pct": True,
            },
        },
    ]

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value={
                "id": "tech",
                "name": "Tech",
                "description": "Test watchlist",
                "tickers": ["AAPL", "MSFT"],
            },
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch(
            "screener.screener.fetch_ohlcv",
            return_value={"AAPL": sample_df, "MSFT": sample_df},
        ),
        patch(
            "screener.screener.compute_indicators",
            side_effect=lambda df, ticker: _make_sample_indicators(ticker),
        ),
        patch("screener.screener.apply_criteria", return_value=apply_results),
    ):
        # Should not raise; --no-ta skips the TA deep-analysis stage.
        main(top_n=2, date_str="2026-03-27", no_ta=True)

    captured = capsys.readouterr()
    # Results table header must appear.
    assert "Rank" in captured.out
    assert "AAPL" in captured.out
    assert "MSFT" in captured.out


# ── Test 6a: sector discovery prints sector-start line (R-UI-12) ──────────────


def test_discovery_prints_sector_fetch_line(capsys):
    """main() in sector mode must print '[Discovery] Fetching top 100 stocks for
    sector: {name}...' before each sector's get_sector_shortlist() call (R-UI-12).
    """
    from screener.screener import main

    sample_df = _make_sample_df()
    minimal_config = _make_minimal_config()
    selected_sectors = minimal_config["sectors"]  # 1 sector: Technology

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=True),
        patch("screener.screener.prompt_sector_selection", return_value=selected_sectors),
        patch(
            "screener.screener.prompt_discovery_criteria",
            return_value=minimal_config["discovery_criteria"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.get_sector_shortlist", return_value=["AAPL", "MSFT"]),
        patch(
            "screener.screener.fetch_ohlcv",
            return_value={"AAPL": sample_df, "MSFT": sample_df},
        ),
        patch(
            "screener.screener.compute_indicators",
            side_effect=lambda df, ticker: _make_sample_indicators(ticker),
        ),
        patch(
            "screener.screener.apply_criteria",
            return_value=[
                {
                    "ticker": "AAPL",
                    "score": 0.8,
                    "indicators": _make_sample_indicators("AAPL"),
                    "filter_results": {k: True for k in ["trend_filter", "rsi_range", "macd_setup", "volume", "atr_pct"]},
                }
            ],
        ),
    ):
        main(top_n=2, date_str="2026-03-27", no_ta=True)

    captured = capsys.readouterr()
    assert "[Discovery] Fetching top 100 stocks for sector: Technology" in captured.out, (
        f"Expected '[Discovery] Fetching top 100 stocks for sector: Technology' in stdout.\n"
        f"Actual stdout:\n{captured.out}"
    )


# ── Test 6: _run_ta_for_ticker marks propagate() failure as ANALYSIS FAILED ───


def test_ta_exception_marked_as_failed():
    """propagate() raising RuntimeError produces an ANALYSIS FAILED result dict."""
    from screener.screener import _run_ta_for_ticker

    mock_ta = MagicMock()
    mock_ta.propagate.side_effect = RuntimeError("Simulated TA failure")

    result = _run_ta_for_ticker(mock_ta, "AAPL", "2026-03-27")

    assert result["decision"] == "ANALYSIS FAILED"
    assert result["ticker"] == "AAPL"
    assert "ANALYSIS FAILED" in result.get("decision", "")
    # confidence must be present
    assert "confidence" in result
    # summary must include the original exception message
    assert "Simulated TA failure" in result["summary"]


# ── Tests 7-9: IB fallback interactive prompt (R-UI-14, R-UI-15) ──────────────


def test_ib_fallback_prompts_user_and_retries(capsys):
    """When fetch_ohlcv raises IBConnectionFailed, main() must prompt the user
    and retry with skip_ib=True if user answers 'y'.
    """
    import datetime
    from screener.screener import main
    from screener.data_fetcher import IBConnectionFailed

    sample_df = _make_sample_df()
    minimal_config = _make_minimal_config()

    ib_exc = IBConnectionFailed("127.0.0.1", 4002, "Connection refused")
    call_count = {"n": 0}

    def fetch_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ib_exc
        return {"AAPL": sample_df, "MSFT": sample_df}

    apply_results = [
        {
            "ticker": "AAPL",
            "score": 0.8,
            "indicators": _make_sample_indicators("AAPL"),
            "filter_results": {k: True for k in ["trend_filter", "rsi_range", "macd_setup", "volume", "atr_pct"]},
        }
    ]

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value=minimal_config["watchlists"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.fetch_ohlcv", side_effect=fetch_side_effect) as mock_fetch,
        patch(
            "screener.screener.compute_indicators",
            side_effect=lambda df, ticker: _make_sample_indicators(ticker),
        ),
        patch("screener.screener.apply_criteria", return_value=apply_results),
        patch("screener.screener._safe_input", return_value="y"),
    ):
        main(top_n=2, date_str="2026-03-27", no_ta=True)

    # fetch_ohlcv called twice: once raising IBConnectionFailed, once with skip_ib=True
    assert mock_fetch.call_count == 2
    second_call_kwargs = mock_fetch.call_args_list[1].kwargs
    assert second_call_kwargs.get("skip_ib") is True, (
        f"Second fetch_ohlcv call must use skip_ib=True; kwargs were: {second_call_kwargs}"
    )


def test_ib_fallback_exits_on_no(capsys):
    """When fetch_ohlcv raises IBConnectionFailed and user answers 'n', exit(1)."""
    from screener.screener import main
    from screener.data_fetcher import IBConnectionFailed

    minimal_config = _make_minimal_config()
    ib_exc = IBConnectionFailed("127.0.0.1", 4002, "Connection refused")

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value=minimal_config["watchlists"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.fetch_ohlcv", side_effect=ib_exc),
        patch("screener.screener._safe_input", return_value="n"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(top_n=2, date_str="2026-03-27", no_ta=True)

    assert exc_info.value.code == 1


# ── Tests 10-13: rate-limit interactive pause (R-UI-16 through R-UI-20) ────────


def test_rate_limit_pause_waits_and_retries(capsys):
    """When fetch_ohlcv raises YFRateLimitExceeded, main() must prompt the user,
    sleep the calculated wait time, and retry fetch_ohlcv.
    """
    import datetime
    import math
    from screener.screener import main
    from screener.yf_rate_limiter import YFRateLimitExceeded

    sample_df = _make_sample_df()
    minimal_config = _make_minimal_config()

    now = datetime.datetime.now(datetime.timezone.utc)
    reset_at = now + datetime.timedelta(seconds=65)
    rl_exc = YFRateLimitExceeded(window="minute", count=100, limit=100, reset_at=reset_at)

    call_count = {"n": 0}

    def fetch_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise rl_exc
        return {"AAPL": sample_df, "MSFT": sample_df}

    apply_results = [
        {
            "ticker": "AAPL",
            "score": 0.8,
            "indicators": _make_sample_indicators("AAPL"),
            "filter_results": {k: True for k in ["trend_filter", "rsi_range", "macd_setup", "volume", "atr_pct"]},
        }
    ]

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value=minimal_config["watchlists"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.fetch_ohlcv", side_effect=fetch_side_effect) as mock_fetch,
        patch(
            "screener.screener.compute_indicators",
            side_effect=lambda df, ticker: _make_sample_indicators(ticker),
        ),
        patch("screener.screener.apply_criteria", return_value=apply_results),
        patch("screener.screener._safe_input", return_value="w"),
        patch("screener.screener.time") as mock_time,
    ):
        main(top_n=2, date_str="2026-03-27", no_ta=True)

    # Must have retried
    assert mock_fetch.call_count == 2
    # Must have slept for approximately wait_secs (65 seconds)
    mock_time.sleep.assert_called_once()
    slept = mock_time.sleep.call_args[0][0]
    assert slept >= 60, f"Expected sleep >= 60s for a 65s window; got {slept}"


def test_rate_limit_pause_stops_on_s(capsys):
    """When fetch_ohlcv raises YFRateLimitExceeded and user enters 's', exit(1)."""
    import datetime
    from screener.screener import main
    from screener.yf_rate_limiter import YFRateLimitExceeded

    minimal_config = _make_minimal_config()
    now = datetime.datetime.now(datetime.timezone.utc)
    rl_exc = YFRateLimitExceeded(
        window="minute", count=100, limit=100, reset_at=now + datetime.timedelta(seconds=30)
    )

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value=minimal_config["watchlists"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.fetch_ohlcv", side_effect=rl_exc),
        patch("screener.screener._safe_input", return_value="s"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(top_n=2, date_str="2026-03-27", no_ta=True)

    assert exc_info.value.code == 1


def test_rate_limit_pause_reprompts_on_invalid_input(capsys):
    """When user enters an invalid response at the rate-limit prompt, re-prompt
    until a valid answer ('w' or 's') is received.
    """
    import datetime
    from screener.screener import main
    from screener.yf_rate_limiter import YFRateLimitExceeded

    minimal_config = _make_minimal_config()
    now = datetime.datetime.now(datetime.timezone.utc)
    rl_exc = YFRateLimitExceeded(
        window="minute", count=100, limit=100, reset_at=now + datetime.timedelta(seconds=10)
    )

    input_responses = iter(["x", "?", "s"])  # two invalid, then stop

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value=minimal_config["watchlists"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.fetch_ohlcv", side_effect=rl_exc),
        patch("screener.screener._safe_input", side_effect=input_responses),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(top_n=2, date_str="2026-03-27", no_ta=True)

    assert exc_info.value.code == 1


def test_rate_limit_wait_secs_clamped_to_minimum(capsys):
    """When exc.reset_at is in the past, wait_secs must be clamped to 1 (minimum)."""
    import datetime
    from screener.screener import main
    from screener.yf_rate_limiter import YFRateLimitExceeded

    sample_df = _make_sample_df()
    minimal_config = _make_minimal_config()

    now = datetime.datetime.now(datetime.timezone.utc)
    # reset_at is in the past — calculated wait_secs would be ≤ 0
    past_reset = now - datetime.timedelta(seconds=30)
    rl_exc = YFRateLimitExceeded(window="minute", count=100, limit=100, reset_at=past_reset)

    call_count = {"n": 0}

    def fetch_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise rl_exc
        return {"AAPL": sample_df, "MSFT": sample_df}

    apply_results = [
        {
            "ticker": "AAPL",
            "score": 0.8,
            "indicators": _make_sample_indicators("AAPL"),
            "filter_results": {k: True for k in ["trend_filter", "rsi_range", "macd_setup", "volume", "atr_pct"]},
        }
    ]

    with (
        patch("screener.screener.load_config", return_value=minimal_config),
        patch("screener.screener.resolve_trade_date", return_value="2026-03-27"),
        patch("screener.screener.prompt_sector_mode", return_value=False),
        patch(
            "screener.screener.prompt_watchlist_selection",
            return_value=minimal_config["watchlists"][0],
        ),
        patch(
            "screener.screener.prompt_screening_criteria",
            return_value=minimal_config["screening_criteria"][0],
        ),
        patch("screener.screener.fetch_ohlcv", side_effect=fetch_side_effect),
        patch(
            "screener.screener.compute_indicators",
            side_effect=lambda df, ticker: _make_sample_indicators(ticker),
        ),
        patch("screener.screener.apply_criteria", return_value=apply_results),
        patch("screener.screener._safe_input", return_value="w"),
        patch("screener.screener.time") as mock_time,
    ):
        main(top_n=2, date_str="2026-03-27", no_ta=True)

    mock_time.sleep.assert_called_once()
    slept = mock_time.sleep.call_args[0][0]
    assert slept >= 1, f"wait_secs must be clamped to minimum 1; got {slept}"
