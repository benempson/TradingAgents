"""Indicator computation engine for the trading screener.

Takes a normalised OHLCV DataFrame and returns a flat dict of the most-recent
trading day's technical indicator values.  Relies on stockstats for the
standard indicator set and computes a small number of manual indicators on top.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from stockstats import wrap

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

_REQUIRED_COLS = {"Date", "Open", "High", "Low", "Close", "Volume"}
_VOL_ROLLING_WINDOW = 20
_RSI_PERIOD = 14
_ATR_PERIOD = 14
_SMA_SHORT = 50
_SMA_LONG = 200
_CROSSOVER_LOOKBACK = 3  # number of recent rows to inspect for MACD-H crossover


# ── helpers ───────────────────────────────────────────────────────────────────


def _safe_last(series: pd.Series) -> Optional[float]:
    """Return the last non-NaN scalar from *series*, or None if all NaN.

    stockstats computes indicators lazily; early rows are often NaN when the
    lookback period has not yet been satisfied.  This helper surfaces those
    gaps as explicit None values so callers can apply hard-filter logic.
    """
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _detect_macdh_crossover(macdh_series: pd.Series, lookback: int = _CROSSOVER_LOOKBACK) -> bool:
    """Return True if the MACD histogram crossed from negative to positive within
    the last *lookback* rows.

    Crossover is defined as: macdh[i-1] < 0 and macdh[i] >= 0 for any i in
    the last *lookback* row indices.  NaN values are treated as neutral (no
    crossover at that position).
    """
    values = macdh_series.dropna().values
    n = len(values)
    if n < 2:
        return False

    # Examine only the last `lookback` indices of the cleaned series.
    start = max(1, n - lookback)
    for i in range(start, n):
        prev = values[i - 1]
        curr = values[i]
        if prev < 0.0 and curr >= 0.0:
            return True
    return False


# ── public interface ──────────────────────────────────────────────────────────


def compute_indicators(df: pd.DataFrame, ticker: str = "UNKNOWN") -> Optional[dict]:
    """Compute technical indicators for the most recent trading day.

    Takes a normalised OHLCV DataFrame (columns: Date, Open, High, Low, Close,
    Volume; sorted ascending by Date) and returns a flat dict of scalar
    indicator values for the last row.

    Indicators that cannot be computed due to insufficient history (e.g.
    SMA-200 requires at least 200 rows) are set to None in the returned dict.
    The caller should treat None on any hard-filter field as disqualification.

    Args:
        df:     OHLCV DataFrame sorted ascending by Date.
        ticker: Ticker symbol used in log messages.

    Returns:
        Dict of indicator values, or None if stockstats raises during wrapping.
    """
    logger.info("Computing indicators", extra={"ticker": ticker, "rows": len(df)})

    # ── wrap in stockstats (works on a copy to avoid mutating caller's df) ──
    try:
        ss_df = wrap(df.copy())
    except Exception:
        logger.error(
            "Indicator computation failed — stockstats.wrap() raised",
            extra={"ticker": ticker},
            exc_info=True,
        )
        return None

    # ── stockstats-derived indicators ────────────────────────────────────────
    n_rows = len(df)
    try:
        rsi = _safe_last(ss_df["rsi"])
        macd = _safe_last(ss_df["macd"])
        macds = _safe_last(ss_df["macds"])
        macdh_series_raw: pd.Series = ss_df["macdh"]
        macdh = _safe_last(macdh_series_raw)

        # Enforce minimum history for SMA indicators — stockstats will backfill
        # with shorter windows when data is scarce, which would produce misleading
        # values.  We surface this as None so hard-filters can disqualify the ticker.
        sma_50 = _safe_last(ss_df["close_50_sma"]) if n_rows >= _SMA_SHORT else None
        sma_200 = _safe_last(ss_df["close_200_sma"]) if n_rows >= _SMA_LONG else None

        atr_series: pd.Series = ss_df["atr"]
        atr = _safe_last(atr_series)
    except Exception:
        logger.error(
            "Indicator computation failed — column access raised after wrap",
            extra={"ticker": ticker},
            exc_info=True,
        )
        return None

    # ── manual indicators (computed directly on the original Close/Volume) ──
    close_series: pd.Series = df["Close"]
    volume_series: pd.Series = df["Volume"]

    close_last = float(close_series.iloc[-1])
    volume_last = float(volume_series.iloc[-1])

    vol_20_avg: Optional[float]
    vol_ratio: Optional[float]
    if len(volume_series) >= _VOL_ROLLING_WINDOW:
        avg = volume_series.rolling(_VOL_ROLLING_WINDOW).mean().iloc[-1]
        if pd.isna(avg) or avg == 0.0:
            vol_20_avg = None
            vol_ratio = None
        else:
            vol_20_avg = float(avg)
            vol_ratio = volume_last / vol_20_avg
    else:
        vol_20_avg = None
        vol_ratio = None
        logger.warning(
            "Insufficient rows for vol_20_avg",
            extra={"ticker": ticker, "rows": len(volume_series), "required": _VOL_ROLLING_WINDOW},
        )

    atr_pct: Optional[float]
    if atr is not None and close_last > 0.0:
        atr_pct = (atr / close_last) * 100.0
    else:
        atr_pct = None

    # ── MACD histogram crossover ─────────────────────────────────────────────
    macdh_crossed_up_3d: bool = _detect_macdh_crossover(macdh_series_raw)

    # Build the full macdh series for downstream composite scoring, filtering
    # NaN values produced by the warmup period.
    macdh_series_list: list[float] = [
        float(v) for v in macdh_series_raw if not pd.isna(v)
    ]

    logger.info(
        "Indicator computation complete",
        extra={
            "ticker": ticker,
            "rsi": rsi,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "macdh_crossed_up_3d": macdh_crossed_up_3d,
            "vol_ratio": vol_ratio,
        },
    )

    return {
        "close": close_last,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "rsi": rsi,
        "macd": macd,
        "macds": macds,
        "macdh": macdh,
        "macdh_crossed_up_3d": macdh_crossed_up_3d,
        "macdh_series": macdh_series_list,
        "atr": atr,
        "atr_pct": atr_pct,
        "volume": volume_last,
        "vol_20_avg": vol_20_avg,
        "vol_ratio": vol_ratio,
    }
