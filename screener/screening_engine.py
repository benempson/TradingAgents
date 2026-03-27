"""
screener/screening_engine.py — R-SCREEN-01 through R-SCREEN-04.

Applies hard filters and composite scoring to a set of pre-computed indicator
dicts, returning a list of passing tickers sorted descending by composite score.

This module has no knowledge of agents, graph, or LLM clients — it is a pure
data-transform layer consistent with the dataflows dependency direction.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────


def _check_trend_filter(ind: dict) -> bool:
    """Return True when close > sma_200. None sma_200 auto-disqualifies."""
    close = ind.get("close")
    sma_200 = ind.get("sma_200")
    if close is None or sma_200 is None:
        return False
    return close > sma_200


def _check_rsi_range(ind: dict, rsi_cfg: dict) -> bool:
    """Return True when rsi is within [min, max]. None rsi auto-disqualifies."""
    rsi = ind.get("rsi")
    if rsi is None:
        return False
    return rsi_cfg["min"] <= rsi <= rsi_cfg["max"]


def _check_macd_setup(ind: dict) -> bool:
    """Return True when macdh > 0 OR macdh_crossed_up_3d is True. None disqualifies."""
    macdh = ind.get("macdh")
    crossed = ind.get("macdh_crossed_up_3d", False)
    if crossed:
        return True
    if macdh is None:
        return False
    return macdh > 0


def _check_volume(ind: dict, vol_cfg: dict) -> bool:
    """Return True when vol_ratio >= min_ratio. None disqualifies."""
    vol_ratio = ind.get("vol_ratio")
    if vol_ratio is None:
        return False
    return vol_ratio >= vol_cfg["min_ratio"]


def _check_atr_pct(ind: dict, atr_cfg: dict) -> bool:
    """Return True when atr_pct is within [min, max]. None disqualifies."""
    atr_pct = ind.get("atr_pct")
    if atr_pct is None:
        return False
    return atr_cfg["min"] <= atr_pct <= atr_cfg["max"]


def _validate_weights(scoring: dict) -> None:
    """Raise ValueError if w1 + w2 + w3 does not sum to 1.0 within tolerance."""
    w1 = scoring.get("w1", 0.0)
    w2 = scoring.get("w2", 0.0)
    w3 = scoring.get("w3", 0.0)
    total = w1 + w2 + w3
    if abs(total - 1.0) >= 1e-6:
        raise ValueError(
            f"Weights w1={w1}, w2={w2}, w3={w3} must sum to 1.0 (got {total:.6f})"
        )


def _compute_score(ind: dict, scoring: dict) -> float:
    """
    Compute composite score using R-SCREEN-03 formula.

    score = w1 * (1 - |rsi - 50| / 50)
          + w2 * ((macdh - hist_min) / (hist_max - hist_min))   [or 0.5 if range == 0]
          + w3 * min(vol_ratio, 3.0) / 3.0
    """
    w1 = scoring["w1"]
    w2 = scoring["w2"]
    w3 = scoring["w3"]

    rsi = ind["rsi"]
    macdh = ind["macdh"]
    vol_ratio = ind["vol_ratio"]
    macdh_series: list[float] = ind.get("macdh_series", [macdh])

    hist_min = min(macdh_series)
    hist_max = max(macdh_series)

    if hist_max == hist_min:
        # Guard against division by zero — set MACD component to neutral 0.5.
        macdh_component = 0.5
    else:
        macdh_component = (macdh - hist_min) / (hist_max - hist_min)

    score = (
        w1 * (1.0 - abs(rsi - 50.0) / 50.0)
        + w2 * macdh_component
        + w3 * min(vol_ratio, 3.0) / 3.0
    )
    return score


# ── public API ────────────────────────────────────────────────────────────────


def apply_criteria(
    indicators_by_ticker: dict[str, dict[str, Any]],
    criteria: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply hard filters then composite scoring to a set of indicator dicts.

    Args:
        indicators_by_ticker: Maps ticker symbol → indicators dict as returned
            by ``compute_indicators``.
        criteria: Parsed JSON object from ``screening_criteria.json`` — one
            criteria entry containing ``hard_filters`` and ``scoring`` sections.

    Returns:
        List of result dicts for tickers that passed all hard filters, sorted
        descending by composite score.  Each dict has the shape defined by
        R-SCREEN-04::

            {
                "ticker": str,
                "score": float,
                "indicators": dict,
                "filter_results": dict,   # keys: trend_filter rsi_range macd_setup volume atr_pct
            }

        Returns ``[]`` when no tickers pass (FM-07 — caller handles messaging).

    Raises:
        ValueError: When scoring weights do not sum to 1.0 within 1e-6 tolerance.
    """
    logger.info(
        "Screening %d tickers with criteria %s",
        len(indicators_by_ticker),
        criteria.get("id"),
    )

    hard_filters = criteria["hard_filters"]
    scoring = criteria["scoring"]

    # Validate weights before touching any ticker data — fail fast at call time.
    _validate_weights(scoring)

    rsi_cfg = hard_filters["rsi"]
    vol_cfg = hard_filters["volume"]
    atr_cfg = hard_filters["atr_pct"]

    results: list[dict[str, Any]] = []

    for ticker, ind in indicators_by_ticker.items():
        filter_results = {
            "trend_filter": _check_trend_filter(ind),
            "rsi_range": _check_rsi_range(ind, rsi_cfg),
            "macd_setup": _check_macd_setup(ind),
            "volume": _check_volume(ind, vol_cfg),
            "atr_pct": _check_atr_pct(ind, atr_cfg),
        }

        all_passed = all(filter_results.values())
        if not all_passed:
            logger.debug(
                "Ticker %s excluded by hard filters: %s",
                ticker,
                {k: v for k, v in filter_results.items() if not v},
            )
            continue

        score = _compute_score(ind, scoring)
        results.append(
            {
                "ticker": ticker,
                "score": score,
                "indicators": ind,
                "filter_results": filter_results,
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)

    logger.info(
        "Screening complete: %d/%d tickers passed",
        len(results),
        len(indicators_by_ticker),
    )

    return results
