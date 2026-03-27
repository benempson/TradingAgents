"""Tests for screener/data_fetcher.py.

Covers the three-source fallback chain (cache → IB → Alpha Vantage → yfinance),
normalisation, and failure modes.  All external dependencies are mocked.
"""

import io
import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from screener.cache_store import CacheStore
from screener.yf_rate_limiter import YFRateLimiter, YFRateLimitExceeded


# ── test helpers ──────────────────────────────────────────────────────────────


def make_yf_dataframe(n: int = 250) -> pd.DataFrame:
    """Synthetic yfinance-style DataFrame with DatetimeIndex.

    Matches the shape that ``yf.download`` returns: a DatetimeIndex named
    "Date" with flat OHLCV columns.
    """
    dates = pd.date_range(end="2026-03-26", periods=n, freq="B")
    rng = np.random.default_rng(42)
    prices = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "Open": prices * 0.99,
            "High": prices * 1.01,
            "Low": prices * 0.98,
            "Close": prices,
            "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=pd.Index(dates, name="Date"),
    )


def make_av_csv(ticker: str = "AAPL", n: int = 250) -> str:
    """Return a minimal Alpha Vantage CSV string matching the adjusted daily format."""
    dates = pd.date_range(end="2026-03-26", periods=n, freq="B")
    rng = np.random.default_rng(7)
    prices = 150 + np.cumsum(rng.normal(0, 1, n))
    rows = ["timestamp,open,high,low,close,adjusted_close,volume,dividend_amount,split_coefficient"]
    for i, d in enumerate(dates):
        p = prices[i]
        rows.append(
            f"{d.strftime('%Y-%m-%d')},{p*0.99:.2f},{p*1.01:.2f},{p*0.98:.2f},{p:.2f},{p:.2f},1000000,0.0,1.0"
        )
    return "\n".join(rows)


def _make_fresh_cache(tmp_path) -> CacheStore:
    """Return a CacheStore backed by a temporary directory."""
    return CacheStore(cache_dir=str(tmp_path / "cache"), validity_mins=480)


def _make_limiter() -> MagicMock:
    """Return a MagicMock that satisfies the YFRateLimiter interface."""
    limiter = MagicMock(spec=YFRateLimiter)
    limiter.check_and_increment.return_value = None
    return limiter


# ── Test 1: cache hit avoids all network sources ───────────────────────────────


def test_fetcher_uses_cache_hit(tmp_path, monkeypatch):
    """A warm cache hit for a ticker skips IB, AV, and yfinance entirely."""
    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()

    # Pre-populate cache with a valid normalised DataFrame.
    cached_df = make_yf_dataframe(250)
    cached_df = cached_df.reset_index()  # expose Date as a column
    cache.put("AAPL_ohlcv_1y", cached_df)

    with (
        patch("screener.data_fetcher.yf") as mock_yf,
        patch("screener.data_fetcher.get_stock") as mock_av,
    ):
        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(["AAPL"], cache, limiter, "2026-03-27")

    assert "AAPL" in result, "Cache-hit ticker must appear in result"
    mock_yf.download.assert_not_called()
    mock_av.assert_not_called()


# ── Test 2: yfinance fallback when IB and AV are both unavailable ──────────────


def test_fetcher_falls_back_to_yfinance_when_ib_unavailable(tmp_path, monkeypatch):
    """Without IB config and without AV key, yfinance is the sole data source."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    yf_df = make_yf_dataframe(250)

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(["MSFT"], cache, limiter, "2026-03-27", ib_host=None)

    assert "MSFT" in result, "yfinance fallback ticker must appear in result"
    df = result["MSFT"]
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"Date", "Open", "High", "Low", "Close", "Volume"}
    # All rows must be before the trade_date cutoff.
    assert (df["Date"] < pd.Timestamp("2026-03-27")).all()
    mock_yf.download.assert_called_once()


# ── Test 3: ticker with no data across all sources is skipped ──────────────────


def test_fetcher_skips_ticker_with_no_data(tmp_path, monkeypatch, caplog):
    """A ticker for which every source returns empty data is omitted from the result."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = pd.DataFrame()  # empty

        with caplog.at_level(logging.WARNING, logger="screener.data_fetcher"):
            from screener.data_fetcher import fetch_ohlcv

            result = fetch_ohlcv(["BADTICKER"], cache, limiter, "2026-03-27", ib_host=None)

    assert "BADTICKER" not in result, "Empty-data ticker must be excluded from result"

    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("BADTICKER" in m for m in warning_messages), (
        "A warning must be logged for the skipped ticker"
    )


# ── Test 4: Alpha Vantage path parses CSV correctly ───────────────────────────


def test_fetcher_alpha_vantage_parses_csv(tmp_path, monkeypatch):
    """When AV key is set and get_stock returns CSV, result is correctly normalised."""
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    av_csv = make_av_csv("TSLA", 250)

    with (
        patch("screener.data_fetcher.get_stock", return_value=av_csv) as mock_av,
        patch("screener.data_fetcher.yf") as mock_yf,
    ):
        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(["TSLA"], cache, limiter, "2026-03-27", ib_host=None)

    assert "TSLA" in result
    df = result["TSLA"]
    assert set(df.columns) == {"Date", "Open", "High", "Low", "Close", "Volume"}
    assert (df["Date"] < pd.Timestamp("2026-03-27")).all()
    mock_av.assert_called_once()
    mock_yf.download.assert_not_called()


# ── Test 5: AV exception falls through to yfinance ───────────────────────────


def test_fetcher_av_exception_falls_through_to_yfinance(tmp_path, monkeypatch):
    """When get_stock() raises, the ticker falls through to yfinance (Source 3)."""
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    yf_df = make_yf_dataframe(250)

    with (
        patch("screener.data_fetcher.get_stock", side_effect=RuntimeError("API down")),
        patch("screener.data_fetcher.yf") as mock_yf,
    ):
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(["GOOG"], cache, limiter, "2026-03-27", ib_host=None)

    assert "GOOG" in result
    mock_yf.download.assert_called_once()


# ── Test 6: YFRateLimitExceeded propagates to caller ─────────────────────────


def test_fetcher_propagates_rate_limit_exceeded(tmp_path, monkeypatch):
    """YFRateLimitExceeded raised by the limiter must propagate out of fetch_ohlcv."""
    import datetime

    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    limiter.check_and_increment.side_effect = YFRateLimitExceeded(
        window="minute",
        count=100,
        limit=100,
        reset_at=datetime.datetime.now(datetime.timezone.utc),
    )

    with patch("screener.data_fetcher.yf"):
        from screener.data_fetcher import fetch_ohlcv

        with pytest.raises(YFRateLimitExceeded):
            fetch_ohlcv(["AMZN"], cache, limiter, "2026-03-27", ib_host=None)


# ── Test 7: all-tickers-fail logs error ───────────────────────────────────────


def test_fetcher_all_tickers_fail_logs_error(tmp_path, monkeypatch, caplog):
    """When every ticker fails from every source, an error is logged and {} returned."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = pd.DataFrame()

        with caplog.at_level(logging.ERROR, logger="screener.data_fetcher"):
            from screener.data_fetcher import fetch_ohlcv

            result = fetch_ohlcv(
                ["BAD1", "BAD2"], cache, limiter, "2026-03-27", ib_host=None
            )

    assert result == {}
    error_messages = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("All tickers failed" in m for m in error_messages), (
        "An error must be logged when all tickers fail"
    )


# ── Test 8: normalise drops partial current-day bar ──────────────────────────


def test_normalise_drops_trade_date_rows(tmp_path, monkeypatch):
    """Rows where Date >= trade_date are stripped by _normalise."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()

    # Include a row for the trade_date itself — it must be dropped.
    dates = pd.date_range(start="2026-03-20", end="2026-03-27", freq="B")
    prices = np.ones(len(dates)) * 100.0
    yf_df = pd.DataFrame(
        {
            "Open": prices,
            "High": prices,
            "Low": prices,
            "Close": prices,
            "Volume": prices * 1000,
        },
        index=pd.Index(dates, name="Date"),
    )

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(["SPY"], cache, limiter, "2026-03-27", ib_host=None)

    assert "SPY" in result
    df = result["SPY"]
    assert pd.Timestamp("2026-03-27") not in df["Date"].values, (
        "trade_date row must be removed by _normalise"
    )


# ── Test 9: AV limit switch to yfinance after 20 calls ───────────────────────


def test_fetcher_av_limit_switches_to_yfinance(tmp_path, monkeypatch):
    """After 20 AV calls in one fetch_ohlcv invocation, remaining tickers use yfinance."""
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()

    av_csv = make_av_csv(n=250)
    yf_df = make_yf_dataframe(250)

    # Generate 25 tickers: first 20 come from AV, last 5 from yfinance.
    tickers = [f"T{i:02d}" for i in range(25)]

    with (
        patch("screener.data_fetcher.get_stock", return_value=av_csv) as mock_av,
        patch("screener.data_fetcher.yf") as mock_yf,
    ):
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(tickers, cache, limiter, "2026-03-27", ib_host=None)

    assert mock_av.call_count == 20, (
        f"Expected exactly 20 AV calls before limit switch, got {mock_av.call_count}"
    )
    assert mock_yf.download.call_count == 5, (
        f"Expected exactly 5 yfinance calls after AV limit, got {mock_yf.download.call_count}"
    )
    assert len(result) == 25


# ── Test 10: result is cached after successful fetch ─────────────────────────


def test_fetcher_writes_to_cache_after_fetch(tmp_path, monkeypatch):
    """After fetching from yfinance, the result is written to the cache."""
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    yf_df = make_yf_dataframe(250)

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        fetch_ohlcv(["NVDA"], cache, limiter, "2026-03-27", ib_host=None)

    # The ticker must now be in the cache.
    cached = cache.get("NVDA_ohlcv_1y")
    assert cached is not None, "Fetched DataFrame must be stored in the cache"
    assert isinstance(cached, pd.DataFrame)


# ── Test 11: dot-ticker cache key sanitisation ─────────────────────────────────


def test_fetcher_handles_dot_ticker_cache_key(tmp_path, monkeypatch):
    """Tickers with exchange suffixes containing dots (e.g. TAP.L for London SE)
    must not raise ValueError from the cache key validator.

    The cache key security regex only allows [A-Za-z0-9_-]. Dots in ticker
    symbols (common in LSE, TSX, ASX listings) must be replaced with hyphens
    before the key is passed to CacheStore — so TAP.L → TAP-L_ohlcv_1y.

    The result dict must still use the original ticker symbol as the key so
    downstream code can look up results by the symbol it submitted.
    """
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    yf_df = make_yf_dataframe(250)

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        # Must not raise ValueError: Cache key 'TAP.L_ohlcv_1y' contains unsafe characters
        result = fetch_ohlcv(["TAP.L"], cache, limiter, "2026-03-27", ib_host=None)

    assert "TAP.L" in result, "Result must be keyed by the original ticker symbol"
    assert isinstance(result["TAP.L"], pd.DataFrame)
    # Verify the sanitised key was used for storage (dot → hyphen)
    assert cache.get("TAP-L_ohlcv_1y") is not None, (
        "Cache entry must be stored under sanitised key 'TAP-L_ohlcv_1y'"
    )


# ── Test 12: per-ticker OHLCV progress lines printed (R-UI-13) ────────────────


def test_fetcher_prints_per_ticker_progress(tmp_path, monkeypatch, capsys):
    """fetch_ohlcv() must print '[Fetcher] Fetching OHLCV for {ticker}: {N} of {total}'
    for each cache-miss ticker (R-UI-13).

    With 3 tickers and an empty cache, all 3 are fetched via yfinance.
    The expected output lines are:
        [Fetcher] Fetching OHLCV for AAPL: 1 of 3
        [Fetcher] Fetching OHLCV for MSFT: 2 of 3
        [Fetcher] Fetching OHLCV for NVDA: 3 of 3
    """
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    yf_df = make_yf_dataframe(250)
    tickers = ["AAPL", "MSFT", "NVDA"]

    with patch("screener.data_fetcher.yf") as mock_yf:
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        fetch_ohlcv(tickers, cache, limiter, "2026-03-27", ib_host=None)

    captured = capsys.readouterr()
    for i, ticker in enumerate(tickers, start=1):
        expected = f"[Fetcher] Fetching OHLCV for {ticker} (yfinance): {i} of {len(tickers)}"
        assert expected in captured.out, (
            f"Expected progress line '{expected}' in stdout.\nActual stdout:\n{captured.out}"
        )


# ── Test 13: IB connection failure raises IBConnectionFailed (R-FETCH-11) ──────


def test_ib_connection_failed_raises(tmp_path, monkeypatch):
    """When IB_HOST is set but connectAsync raises ConnectionRefusedError,
    _fetch_ib must propagate IBConnectionFailed instead of silently returning {}.

    The test verifies that fetch_ohlcv (with ib_host explicitly set) raises
    IBConnectionFailed when the IB connection is refused.
    """
    import asyncio
    from screener.data_fetcher import IBConnectionFailed, fetch_ohlcv

    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()

    # Patch the IB class inside data_fetcher so connectAsync raises ConnectionRefusedError.
    mock_ib_instance = MagicMock()
    mock_ib_instance.connectAsync = MagicMock(
        side_effect=ConnectionRefusedError("Connection refused")
    )

    with patch("screener.data_fetcher.IB", return_value=mock_ib_instance):
        with pytest.raises(IBConnectionFailed) as exc_info:
            fetch_ohlcv(["AAPL"], cache, limiter, "2026-03-27", ib_host="127.0.0.1")

    assert "127.0.0.1" in str(exc_info.value) or exc_info.value.host == "127.0.0.1"


# ── Test 14: skip_ib=True bypasses IB even when IB_HOST is configured ──────────


def test_fetch_ohlcv_skip_ib_bypasses_ib(tmp_path, monkeypatch):
    """When skip_ib=True is passed to fetch_ohlcv, IB must not be attempted
    regardless of ib_host or IB_HOST env var.
    """
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.setenv("IB_HOST", "127.0.0.1")

    cache = _make_fresh_cache(tmp_path)
    limiter = _make_limiter()
    yf_df = make_yf_dataframe(250)

    mock_ib_class = MagicMock()

    with (
        patch("screener.data_fetcher.IB", mock_ib_class),
        patch("screener.data_fetcher.yf") as mock_yf,
    ):
        mock_yf.download.return_value = yf_df

        from screener.data_fetcher import fetch_ohlcv

        result = fetch_ohlcv(["AAPL"], cache, limiter, "2026-03-27", skip_ib=True)

    # IB class must never have been instantiated
    mock_ib_class.assert_not_called()
    assert "AAPL" in result
