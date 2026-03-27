"""
Tests for screener/screening_engine.py — R-SCREEN-01 through R-SCREEN-04.

Run:
    python -m pytest tests/test_screener_screening.py -v
"""

import pytest
from screener.screening_engine import apply_criteria

# ── constants ─────────────────────────────────────────────────────────────────

SAMPLE_CRITERIA = {
    "id": "default",
    "name": "Default",
    "hard_filters": {
        "rsi": {"min": 35, "max": 65},
        "volume": {"min_ratio": 1.2},
        "atr_pct": {"min": 0.5, "max": 5.0},
    },
    "scoring": {"w1": 0.4, "w2": 0.4, "w3": 0.2},
}

# ── helpers ───────────────────────────────────────────────────────────────────


def make_indicators(
    close: float = 150.0,
    sma_50: float = 140.0,
    sma_200: float = 130.0,
    rsi: float = 50.0,
    macdh: float = 0.5,
    macdh_crossed: bool = False,
    vol_ratio: float = 1.5,
    atr_pct: float = 1.0,
) -> dict:
    """Build a complete indicators dict compatible with apply_criteria()."""
    return {
        "close": close,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "rsi": rsi,
        "macdh": macdh,
        "macdh_crossed_up_3d": macdh_crossed,
        "vol_ratio": vol_ratio,
        "atr_pct": atr_pct,
        # Full 1Y MACD histogram series used for composite score normalisation.
        "macdh_series": [0.1, 0.2, 0.5],
    }


# ── filter tests ──────────────────────────────────────────────────────────────


def test_ticker_fails_trend_filter():
    """Ticker with close < sma_200 must be excluded from results (R-SCREEN-02 trend_filter)."""
    indicators = {
        "AAPL": make_indicators(close=90.0, sma_200=100.0),
    }
    results = apply_criteria(indicators, SAMPLE_CRITERIA)
    tickers = [r["ticker"] for r in results]
    assert "AAPL" not in tickers, (
        "Ticker with close < sma_200 should be excluded by trend_filter"
    )


def test_ticker_fails_rsi_range():
    """Ticker with rsi=70 exceeds default max=65 and must be excluded (R-SCREEN-02 rsi_range)."""
    indicators = {
        "TSLA": make_indicators(rsi=70.0),
    }
    results = apply_criteria(indicators, SAMPLE_CRITERIA)
    tickers = [r["ticker"] for r in results]
    assert "TSLA" not in tickers, (
        "Ticker with RSI=70 should fail rsi_range filter (max=65)"
    )


# ── scoring and ordering tests ────────────────────────────────────────────────


def test_composite_score_order():
    """
    Three tickers all passing filters — results must be sorted descending by composite score,
    and each score must match the formula from R-SCREEN-03.
    """
    # Ticker A: RSI=45 (close to 50), macdh=0.5, vol_ratio=2.0  → high score
    ind_a = make_indicators(rsi=45.0, macdh=0.5, vol_ratio=2.0)
    # Ticker B: RSI=35 (boundary, further from 50), macdh=0.2, vol_ratio=1.3  → mid score
    ind_b = make_indicators(rsi=35.0, macdh=0.2, vol_ratio=1.3)
    # Ticker C: RSI=60, macdh=0.1, vol_ratio=1.2  → lowest score
    ind_c = make_indicators(rsi=60.0, macdh=0.1, vol_ratio=1.2)

    indicators = {"A": ind_a, "B": ind_b, "C": ind_c}
    results = apply_criteria(indicators, SAMPLE_CRITERIA)

    assert len(results) == 3, "All three tickers should pass filters"

    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), (
        "Results must be sorted descending by composite score"
    )

    # Verify exact score for ticker A using R-SCREEN-03 formula.
    w1, w2, w3 = 0.4, 0.4, 0.2
    hist_min = min(ind_a["macdh_series"])  # 0.1
    hist_max = max(ind_a["macdh_series"])  # 0.5
    expected_score_a = (
        w1 * (1 - abs(45.0 - 50) / 50)
        + w2 * ((0.5 - hist_min) / (hist_max - hist_min))
        + w3 * min(2.0, 3.0) / 3.0
    )
    result_a = next(r for r in results if r["ticker"] == "A")
    assert abs(result_a["score"] - expected_score_a) < 1e-9, (
        f"Score for A: expected {expected_score_a}, got {result_a['score']}"
    )


# ── weight validation tests ───────────────────────────────────────────────────


def test_weights_must_sum_to_one():
    """Weights summing to != 1.0 must raise ValueError (R-SCREEN-03 validation)."""
    bad_criteria = {
        "id": "bad",
        "name": "Bad weights",
        "hard_filters": {
            "rsi": {"min": 35, "max": 65},
            "volume": {"min_ratio": 1.2},
            "atr_pct": {"min": 0.5, "max": 5.0},
        },
        "scoring": {"w1": 0.4, "w2": 0.4, "w3": 0.3},  # sum = 1.1
    }
    indicators = {"AAPL": make_indicators()}
    with pytest.raises(ValueError, match="[Ww]eight"):
        apply_criteria(indicators, bad_criteria)


# ── result structure tests ────────────────────────────────────────────────────


def test_result_dict_structure():
    """Each result dict must contain ticker, score, indicators, filter_results (R-SCREEN-04)."""
    indicators = {"MSFT": make_indicators()}
    results = apply_criteria(indicators, SAMPLE_CRITERIA)
    assert len(results) == 1
    r = results[0]
    assert "ticker" in r
    assert "score" in r
    assert "indicators" in r
    assert "filter_results" in r
    assert isinstance(r["filter_results"], dict)
    # filter_results must contain the five defined filter names
    expected_keys = {"trend_filter", "rsi_range", "macd_setup", "volume", "atr_pct"}
    assert expected_keys == set(r["filter_results"].keys())


def test_empty_result_on_all_fail():
    """When no tickers pass filters, apply_criteria returns [] without raising (FM-07)."""
    indicators = {"FAIL": make_indicators(close=80.0, sma_200=100.0)}  # trend fail
    results = apply_criteria(indicators, SAMPLE_CRITERIA)
    assert results == []


def test_sma_200_none_auto_disqualifies():
    """Ticker with sma_200=None is auto-disqualified (R-SCREEN-02)."""
    ind = make_indicators()
    ind["sma_200"] = None
    results = apply_criteria({"XYZ": ind}, SAMPLE_CRITERIA)
    assert results == []


def test_macdh_crossed_up_passes_macd_filter():
    """Ticker with macdh < 0 but macdh_crossed_up_3d=True should pass macd_setup (R-SCREEN-02)."""
    ind = make_indicators(macdh=-0.1, macdh_crossed=True)
    results = apply_criteria({"TICK": ind}, SAMPLE_CRITERIA)
    tickers = [r["ticker"] for r in results]
    assert "TICK" in tickers, (
        "macdh_crossed_up_3d=True should satisfy macd_setup even when macdh < 0"
    )


def test_macdh_hist_equal_score_component():
    """
    When macdh_series has all equal values (hist_min == hist_max), the macdh score
    component must be 0.5 to avoid division by zero (R-SCREEN-03).
    """
    ind = make_indicators(macdh=0.3)
    ind["macdh_series"] = [0.3, 0.3, 0.3]  # all equal → hist_min == hist_max
    w1, w2, w3 = 0.4, 0.4, 0.2
    expected = (
        w1 * (1 - abs(50.0 - 50) / 50)
        + w2 * 0.5  # division-by-zero guard
        + w3 * min(1.5, 3.0) / 3.0
    )
    results = apply_criteria({"EQ": ind}, SAMPLE_CRITERIA)
    assert len(results) == 1
    assert abs(results[0]["score"] - expected) < 1e-9
