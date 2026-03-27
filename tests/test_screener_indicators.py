"""Tests for screener/indicator_engine.py — TDD suite.

Tests are written first (red phase). Run with:
    python -m pytest tests/test_screener_indicators.py -v
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from screener.indicator_engine import compute_indicators

# ── helpers ───────────────────────────────────────────────────────────────────


def make_ohlcv(n_rows: int, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic but realistic OHLCV DataFrame.

    Produces n_rows rows sorted ascending by Date starting 2024-01-01.
    Prices fluctuate around 100.0 via a random walk; volume around 1e6.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start="2024-01-01", periods=n_rows, freq="B")

    # Random walk for close prices around 100.0
    returns = rng.normal(loc=0.0001, scale=0.01, size=n_rows)
    close = 100.0 * np.cumprod(1 + returns)

    # High/Low/Open derived from close with small noise
    noise = rng.uniform(0.001, 0.02, size=n_rows)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = close * (1 + rng.normal(0, 0.005, size=n_rows))

    volume = rng.normal(loc=1_000_000, scale=100_000, size=n_rows).clip(min=1)

    return pd.DataFrame(
        {
            "Date": dates,
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        }
    )


def _make_stockstats_mock(macdh_values: list[float]) -> MagicMock:
    """Build a minimal mock that looks like a stockstats-wrapped DataFrame.

    Returns a MagicMock whose column-access (`__getitem__`) returns Series
    with the supplied macdh_values and sensible defaults for other indicators.
    """
    n = len(macdh_values)
    close_prices = np.linspace(95, 105, n)
    volume = np.full(n, 1_000_000.0)

    def getitem(key: str) -> pd.Series:
        series_map = {
            "rsi": pd.Series(np.full(n, 55.0)),
            "macd": pd.Series(np.full(n, 0.5)),
            "macds": pd.Series(np.full(n, 0.4)),
            "macdh": pd.Series(macdh_values, dtype=float),
            "close_50_sma": pd.Series(np.full(n, 100.0)),
            "close_200_sma": pd.Series(np.full(n, 98.0)),
            "atr": pd.Series(np.full(n, 1.5)),
            "close": pd.Series(close_prices),
            "volume": pd.Series(volume),
        }
        return series_map.get(key, pd.Series(np.zeros(n)))

    mock_df = MagicMock(spec=pd.DataFrame)
    mock_df.__getitem__ = MagicMock(side_effect=getitem)
    mock_df.__len__ = MagicMock(return_value=n)

    # Also expose the columns that compute_indicators accesses directly on the df
    mock_df["close"] = pd.Series(close_prices)
    mock_df["volume"] = pd.Series(volume)

    return mock_df


# ── tests ─────────────────────────────────────────────────────────────────────


class TestComputeIndicatorsFullHistory:
    """R-IND-01 through R-IND-04 with a 250-row history."""

    def test_indicators_computed_correctly(self):
        """250-row DataFrame should return a fully-populated indicator dict."""
        df = make_ohlcv(250)
        result = compute_indicators(df, ticker="TEST")

        assert result is not None, "Expected a dict, got None"

        # All keys must be present
        expected_keys = {
            "close", "sma_50", "sma_200", "rsi", "macd", "macds",
            "macdh", "macdh_crossed_up_3d", "macdh_series",
            "atr", "atr_pct", "volume", "vol_20_avg", "vol_ratio",
        }
        assert expected_keys == set(result.keys()), (
            f"Missing keys: {expected_keys - set(result.keys())}"
        )

        # RSI must be in 0-100
        assert result["rsi"] is not None
        assert 0.0 <= result["rsi"] <= 100.0, f"RSI out of range: {result['rsi']}"

        # Volume ratio must be positive
        assert result["vol_ratio"] is not None
        assert result["vol_ratio"] > 0, f"vol_ratio not positive: {result['vol_ratio']}"

        # ATR percentage must be positive
        assert result["atr_pct"] is not None
        assert result["atr_pct"] > 0, f"atr_pct not positive: {result['atr_pct']}"

        # SMA-50 and SMA-200 must be populated given 250 rows
        assert result["sma_50"] is not None, "sma_50 should not be None with 250 rows"
        assert result["sma_200"] is not None, "sma_200 should not be None with 250 rows"

        # macdh_series must be a list of floats
        assert isinstance(result["macdh_series"], list)
        assert len(result["macdh_series"]) > 0
        assert all(isinstance(v, float) for v in result["macdh_series"])

        # macdh_crossed_up_3d must be a bool
        assert isinstance(result["macdh_crossed_up_3d"], bool)

        # close and volume must be positive scalars
        assert result["close"] > 0
        assert result["volume"] > 0


class TestComputeIndicatorsShortHistory:
    """R-IND-05: insufficient data handling."""

    def test_indicators_returns_none_for_sma200_with_short_history(self):
        """100-row DataFrame: sma_200 should be None; close/rsi/sma_50 populated."""
        df = make_ohlcv(100)
        result = compute_indicators(df, ticker="SHORT")

        assert result is not None, "Expected a dict (not None) even for short history"

        # sma_200 requires 200 periods — must be None
        assert result["sma_200"] is None, (
            f"Expected sma_200=None with 100 rows, got {result['sma_200']}"
        )

        # These should still have valid values with 100 rows
        assert result["close"] is not None and result["close"] > 0
        assert result["rsi"] is not None, "RSI should be computable from 100 rows"
        assert result["sma_50"] is not None, "SMA-50 should be computable from 100 rows"


class TestMacdCrossover:
    """R-IND-04: MACD histogram crossover detection."""

    def test_macdh_crossed_up_3d_true(self):
        """macdh crossing from negative to positive in last 3 rows → True."""
        # Build a macdh series where the last two values are [..., -0.01, 0.02]
        n = 50
        macdh_values = [0.1] * (n - 2) + [-0.01, 0.02]

        df_input = make_ohlcv(n)

        with patch("screener.indicator_engine.wrap") as mock_wrap:
            mock_ss = _make_stockstats_mock(macdh_values)
            mock_wrap.return_value = mock_ss

            # We need the mock to behave like a real DataFrame for the non-stockstats
            # accesses (Volume, Close, iloc). Use the real df for those paths.
            result = compute_indicators(df_input, ticker="CROSS_UP")

        assert result is not None
        assert result["macdh_crossed_up_3d"] is True, (
            "Expected macdh_crossed_up_3d=True when macdh crosses -0.01 → 0.02"
        )

    def test_macdh_crossed_up_3d_false(self):
        """All last 3 macdh values positive (no recent crossover) → False."""
        n = 50
        # All positive — no crossover
        macdh_values = [0.1] * (n - 3) + [0.05, 0.07, 0.09]

        df_input = make_ohlcv(n)

        with patch("screener.indicator_engine.wrap") as mock_wrap:
            mock_ss = _make_stockstats_mock(macdh_values)
            mock_wrap.return_value = mock_ss

            result = compute_indicators(df_input, ticker="NO_CROSS")

        assert result is not None
        assert result["macdh_crossed_up_3d"] is False, (
            "Expected macdh_crossed_up_3d=False when all last 3 macdh values are positive"
        )


class TestErrorHandling:
    """R-IND-06: stockstats failure returns None for entire dict."""

    def test_stockstats_exception_returns_none(self):
        """If stockstats.wrap() raises, compute_indicators returns None."""
        df = make_ohlcv(250)

        with patch("screener.indicator_engine.wrap", side_effect=RuntimeError("boom")):
            result = compute_indicators(df, ticker="ERR")

        assert result is None, "Expected None when stockstats.wrap() raises"
