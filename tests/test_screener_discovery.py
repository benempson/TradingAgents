"""Tests for screener/discovery.py — sector shortlist discovery via yfinance screen().

All tests mock ``yf.screen`` to avoid real network calls.
The yfinance API used is ``yf.screen(EquityQuery(...), size=100, ...)`` (yfinance ≥ 1.2.0).
"""

import glob
import json
import logging
from unittest.mock import MagicMock, call, patch

import pytest
from yfinance import EquityQuery

from screener.discovery import get_sector_shortlist, _run_screener


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_quotes(n: int) -> list[dict]:
    """Generate n synthetic quote dicts with unique symbols."""
    return [{"symbol": f"T{i}"} for i in range(n)]


def _make_limiter() -> MagicMock:
    """Return a mock YFRateLimiter that always succeeds."""
    m = MagicMock()
    m.check_and_increment.return_value = None
    return m


def _screen_response(quotes: list[dict]) -> dict:
    """Wrap quotes in a yf.screen-style response dict."""
    return {"quotes": quotes, "start": 0, "count": len(quotes), "total": len(quotes)}


# ── test 1: zero results ──────────────────────────────────────────────────────

def test_discovery_returns_empty_on_zero_results(tmp_path, caplog):
    """When the screener returns no quotes, get_sector_shortlist returns [] and logs a warning."""
    mock_limiter = _make_limiter()

    with caplog.at_level(logging.WARNING, logger="screener.discovery"):
        with patch("screener.discovery.yf.screen", return_value=_screen_response([])):
            with patch("screener.discovery.EquityQuery"):
                result = get_sector_shortlist(
                    "tech",
                    "Technology",
                    {"id": "momentum", "filters": []},
                    mock_limiter,
                    str(tmp_path),
                )

    assert result == []
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_messages) >= 1, "Expected at least one WARNING log for zero results"


# ── test 2: 100-ticker cap ────────────────────────────────────────────────────

def test_discovery_caps_at_100(tmp_path):
    """When the screener returns >100 quotes, get_sector_shortlist returns at most 100."""
    mock_limiter = _make_limiter()

    with patch("screener.discovery.yf.screen", return_value=_screen_response(_make_quotes(150))):
        with patch("screener.discovery.EquityQuery"):
            result = get_sector_shortlist(
                "tech",
                "Technology",
                {"id": "momentum", "filters": []},
                mock_limiter,
                str(tmp_path),
            )

    assert len(result) == 100


# ── test 3: result file is saved correctly ────────────────────────────────────

def test_discovery_saves_result_file(tmp_path):
    """get_sector_shortlist writes a correctly-structured JSON result file."""
    quotes = [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "GOOG"}]
    mock_limiter = _make_limiter()

    with patch("screener.discovery.yf.screen", return_value=_screen_response(quotes)):
        with patch("screener.discovery.EquityQuery"):
            result = get_sector_shortlist(
                "technology",
                "Technology",
                {"id": "momentum", "filters": []},
                mock_limiter,
                str(tmp_path),
            )

    assert result == ["AAPL", "MSFT", "GOOG"]

    files = glob.glob(str(tmp_path / "sector_filters_*.json"))
    assert len(files) == 1, f"Expected exactly one result file, found: {files}"

    with open(files[0], encoding="utf-8") as fh:
        data = json.load(fh)

    assert data["ticker_count"] == 3
    assert data["tickers"] == ["AAPL", "MSFT", "GOOG"]
    assert data["sector_key"] == "technology"
    assert "run_at" in data
    assert data["discovery_criteria_id"] == "momentum"


# ── test 4: API exception returns [] ─────────────────────────────────────────

def test_discovery_returns_empty_on_api_error(tmp_path, caplog):
    """When yf.screen raises an exception, get_sector_shortlist returns [] and logs an error."""
    mock_limiter = _make_limiter()

    with caplog.at_level(logging.ERROR, logger="screener.discovery"):
        with patch("screener.discovery.yf.screen", side_effect=RuntimeError("yfinance API unavailable")):
            with patch("screener.discovery.EquityQuery"):
                result = get_sector_shortlist(
                    "tech",
                    "Technology",
                    {"id": "momentum", "filters": []},
                    mock_limiter,
                    str(tmp_path),
                )

    assert result == []
    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_messages) >= 1, "Expected at least one ERROR log for API failure"


# ── test 5: rate limiter is called before yf.screen ──────────────────────────

def test_discovery_calls_rate_limiter(tmp_path):
    """get_sector_shortlist calls limiter.check_and_increment() before calling yf.screen."""
    mock_limiter = _make_limiter()

    call_order: list[str] = []
    mock_limiter.check_and_increment.side_effect = lambda: call_order.append("limiter")

    def screen_side_effect(*args, **kwargs) -> dict:
        call_order.append("screen")
        return _screen_response([{"symbol": "AAPL"}])

    with patch("screener.discovery.yf.screen", side_effect=screen_side_effect):
        with patch("screener.discovery.EquityQuery"):
            get_sector_shortlist(
                "tech",
                "Technology",
                {"id": "momentum", "filters": []},
                mock_limiter,
                str(tmp_path),
            )

    mock_limiter.check_and_increment.assert_called_once()
    assert call_order.index("limiter") < call_order.index("screen"), (
        "check_and_increment() must be called before yf.screen"
    )


# ── test 6: dict filters from config are converted to EquityQuery objects ─────

def test_run_screener_converts_dict_filters_to_equity_query(tmp_path):
    """_run_screener must convert filter dicts loaded from discovery_criteria.json into
    EquityQuery instances before constructing the AND query.

    discovery_criteria.json stores filters as plain dicts, e.g.:
        {"operator": "GT", "operands": ["percentchange", 0]}

    Passing these raw dicts to EquityQuery("and", [...]) raises:
        TypeError: Operand must be type <class 'yfinance.screener.query.EquityQuery'> for OR/AND
    """
    dict_filters = [
        {"operator": "GT", "operands": ["percentchange", 0]},
        {"operator": "GT", "operands": ["dayvolume", 1000000]},
    ]

    with patch("screener.discovery.yf.screen", return_value={"quotes": [{"symbol": "AAPL"}]}) as mock_screen:
        result = _run_screener("Technology", dict_filters)

    assert result == ["AAPL"]
    mock_screen.assert_called_once()
    # The first positional arg to yf.screen must be an EquityQuery (not a raw dict).
    screen_query_arg = mock_screen.call_args[0][0]
    assert isinstance(screen_query_arg, EquityQuery), (
        f"yf.screen was called with a {type(screen_query_arg).__name__}, expected EquityQuery"
    )
