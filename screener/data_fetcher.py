"""OHLCV data fetcher for the screener package.

Implements a three-source fallback chain per ticker:

  0. Cache (CacheStore) — fastest path; no network call.
  1. IB Gateway (ib_async) — optional; only used when ``ib_host`` / ``ib_port``
     are supplied (or set via env vars).
  2. Alpha Vantage — used when ``ALPHA_VANTAGE_API_KEY`` is set; capped at 20
     calls per ``fetch_ohlcv()`` invocation to stay clear of the daily limit.
  3. yfinance — the always-available last resort.

All DataFrames are normalised to the canonical five-column schema:
``[Date, Open, High, Low, Close, Volume]`` before being returned or cached.

Raises
------
YFRateLimitExceeded
    Propagated from ``YFRateLimiter.check_and_increment()`` when the rolling
    yfinance rate window is exhausted.  The caller (``screener.py``) is
    responsible for deciding how to proceed.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import TYPE_CHECKING

import pandas as pd
import yfinance as yf

from screener.cache_store import CacheStore
from screener.yf_rate_limiter import YFRateLimiter, YFRateLimitExceeded
from tradingagents.dataflows.alpha_vantage_stock import get_stock
from tradingagents.dataflows.stockstats_utils import yf_retry

# Guard optional ib_async dependency — the library may not be installed in all
# environments.  If absent, the IB source is silently skipped.
try:
    from ib_async import IB, Stock, util  # type: ignore[import-not-found]
except ImportError:
    IB = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

# Maximum Alpha Vantage calls per fetch_ohlcv() invocation before switching
# remaining tickers to yfinance.  The AV free tier allows 25 calls/day; we
# leave a safety buffer of 5.
_AV_CALL_LIMIT = 20

# Inter-request delay for IB Gateway (seconds).  Kept short for testability;
# in production set IB_REQUEST_DELAY_S env var if a longer pause is required.
_IB_REQUEST_DELAY_S: float = float(os.environ.get("IB_REQUEST_DELAY_S", "0.1"))


# ── IB async helper ───────────────────────────────────────────────────────────


async def _fetch_ib_async(
    tickers: list[str],
    host: str,
    port: int,
    client_id: int,
) -> dict[str, pd.DataFrame]:
    """Fetch 1-year daily adjusted bars from IB Gateway for every ticker.

    Args:
        tickers: List of ticker symbols.
        host: IB Gateway host address.
        port: IB Gateway port number.
        client_id: IB client ID.

    Returns:
        Dict mapping ticker → raw DataFrame (DatetimeIndex, OHLCV columns).
        Tickers that raise an individual error are omitted silently after
        logging a warning.
    """
    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id)
    except (ConnectionRefusedError, asyncio.TimeoutError) as exc:
        logger.warning(
            "IB Gateway connection failed — skipping IB source",
            extra={"host": host, "port": port, "error": str(exc)},
        )
        return {}

    results: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            contract = Stock(ticker, "SMART", "USD")
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="1 Y",
                barSizeSetting="1 day",
                whatToShow="ADJUSTED_LAST",
                useRTH=True,
            )
            if bars:
                df = util.df(bars)
                df = df.rename(
                    columns={
                        "date": "Date",
                        "open": "Open",
                        "high": "High",
                        "low": "Low",
                        "close": "Close",
                        "volume": "Volume",
                    }
                )
                results[ticker] = df
                logger.info(
                    "IB fetch success",
                    extra={"ticker": ticker, "rows": len(df)},
                )
            else:
                logger.warning(
                    "IB returned empty bars for ticker",
                    extra={"ticker": ticker},
                )
        except Exception as exc:  # noqa: BLE001 — individual ticker errors must not abort the loop
            logger.warning(
                "IB fetch error for ticker — skipping",
                extra={"ticker": ticker, "error": str(exc)},
                exc_info=True,
            )
        await asyncio.sleep(_IB_REQUEST_DELAY_S)

    ib.disconnect()
    logger.info(
        "IB fetch complete",
        extra={"fetched": len(results), "requested": len(tickers)},
    )
    return results


def _fetch_ib(
    tickers: list[str],
    host: str,
    port: int,
    client_id: int,
) -> dict[str, pd.DataFrame]:
    """Synchronous wrapper around ``_fetch_ib_async``.

    Runs the async helper in a new event loop so it can be called from
    synchronous contexts without blocking a running loop.

    Returns:
        Dict mapping ticker → raw DataFrame.  Empty dict on connection failure.
    """
    return asyncio.run(_fetch_ib_async(tickers, host, port, client_id))


# ── Alpha Vantage CSV parsing ─────────────────────────────────────────────────


def _parse_av_csv(csv_str: str) -> pd.DataFrame | None:
    """Parse an Alpha Vantage daily-adjusted CSV string into a raw DataFrame.

    The AV response uses ``adjusted_close`` as the canonical close price.
    Non-OHLCV columns (dividend, split coefficient) are dropped.

    Args:
        csv_str: Raw CSV string from ``get_stock()``.

    Returns:
        DataFrame with columns ``[Date, Open, High, Low, Close, Volume]`` or
        ``None`` if the string is empty or cannot be parsed.
    """
    if not csv_str or not csv_str.strip():
        return None

    try:
        df = pd.read_csv(io.StringIO(csv_str))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to parse Alpha Vantage CSV",
            extra={"error": str(exc)},
            exc_info=True,
        )
        return None

    # AV columns: timestamp, open, high, low, close, adjusted_close, volume, ...
    rename_map: dict[str, str] = {
        "timestamp": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "adjusted_close": "Close",  # use adjusted close as canonical Close
        "volume": "Volume",
    }
    df = df.rename(columns=rename_map)

    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        logger.warning(
            "Alpha Vantage CSV missing expected columns",
            extra={"missing": sorted(missing)},
        )
        return None

    return df[list(required)]


# ── normalisation ─────────────────────────────────────────────────────────────


def _normalise(df: pd.DataFrame, trade_date: str) -> pd.DataFrame | None:
    """Normalise an OHLCV DataFrame into the canonical schema.

    Steps performed:
    1. Ensure a ``Date`` column exists (reset DatetimeIndex if necessary).
    2. Parse ``Date`` to datetime; drop unparseable rows.
    3. Coerce price/volume columns to float64; drop rows with NaN ``Close``.
    4. Drop rows where ``Date.date() >= trade_date`` (avoid partial current-day bars).
    5. Sort ascending and reset the integer index.
    6. Return ``None`` if the resulting DataFrame is empty.

    Args:
        df: Raw OHLCV DataFrame from any source.
        trade_date: Cutoff date string in ``YYYY-MM-DD`` format.  Rows on or
            after this date are excluded.

    Returns:
        Normalised DataFrame with columns ``[Date, Open, High, Low, Close,
        Volume]``, or ``None`` if no rows survive the filter.
    """
    if "Date" not in df.columns:
        df = df.reset_index()

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Close"])

    cutoff = pd.Timestamp(trade_date).date()
    df = df[df["Date"].dt.date < cutoff]

    df = df.sort_values("Date").reset_index(drop=True)

    if df.empty:
        return None

    # Keep only the canonical five columns; add any missing ones as NaN so the
    # schema is consistent even if a source omits e.g. Volume.
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            df[col] = float("nan")

    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


# ── main public function ───────────────────────────────────────────────────────


def fetch_ohlcv(
    tickers: list[str],
    cache: CacheStore,
    limiter: YFRateLimiter,
    trade_date: str,
    ib_host: str | None = None,
    ib_port: int | None = None,
    ib_client_id: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch 1-year daily OHLCV data for each ticker using a three-source fallback chain.

    Fallback order per ticker:
      0. Cache — returned immediately on hit; no network call.
      1. IB Gateway — only when ``ib_host``/``ib_port`` are available.
      2. Alpha Vantage — only when ``ALPHA_VANTAGE_API_KEY`` env var is set;
         capped at ``_AV_CALL_LIMIT`` calls per invocation.
      3. yfinance — last resort; rate-limited by ``limiter``.

    All DataFrames are normalised before being returned and written to cache.

    Args:
        tickers: List of ticker symbols to fetch.
        cache: CacheStore instance for read/write operations.
        limiter: YFRateLimiter instance; ``check_and_increment()`` is called
            before each yfinance download.
        trade_date: Reference date in ``YYYY-MM-DD`` format.  Rows on or after
            this date are stripped from every DataFrame.
        ib_host: IB Gateway hostname or IP.  If ``None``, IB is skipped.
        ib_port: IB Gateway port.  Falls back to ``IB_PORT`` env var or 4002.
        ib_client_id: IB client ID.  Falls back to ``IB_CLIENT_ID`` env var or 10.

    Returns:
        Dict mapping ticker symbol → normalised OHLCV DataFrame.  Tickers for
        which all sources returned empty data are omitted.

    Raises:
        YFRateLimitExceeded: Propagated from ``limiter.check_and_increment()``
            when the rolling yfinance window is exhausted.
    """
    # Resolve IB connection parameters from args, then env vars, then defaults.
    resolved_ib_host: str | None = ib_host or os.environ.get("IB_HOST")
    resolved_ib_port: int = ib_port or int(os.environ.get("IB_PORT", "4002"))
    resolved_ib_client_id: int = ib_client_id or int(os.environ.get("IB_CLIENT_ID", "10"))

    av_api_key: str | None = os.environ.get("ALPHA_VANTAGE_API_KEY")

    # Compute AV date range once — one year before trade_date up to trade_date.
    trade_ts = pd.Timestamp(trade_date)
    av_start = (trade_ts - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    av_end = trade_date

    result: dict[str, pd.DataFrame] = {}
    pending_after_cache: list[str] = []

    # ── Source 0: Cache ────────────────────────────────────────────────────────
    for ticker in tickers:
        cached = cache.get(f"{ticker}_ohlcv_1y")
        if cached is not None:
            logger.info("Cache hit for %s", ticker)
            result[ticker] = cached
        else:
            pending_after_cache.append(ticker)

    if not pending_after_cache:
        return result

    # ── Source 1: IB Gateway ──────────────────────────────────────────────────
    pending_after_ib: list[str] = list(pending_after_cache)

    if resolved_ib_host is not None:
        if IB is None:
            logger.warning(
                "IB host/port configured but ib_async is not installed — skipping IB source",
                extra={"ib_host": resolved_ib_host, "ib_port": resolved_ib_port},
            )
        else:
            logger.info(
                "Attempting IB fetch",
                extra={
                    "tickers": pending_after_cache,
                    "host": resolved_ib_host,
                    "port": resolved_ib_port,
                },
            )
            ib_raw = _fetch_ib(
                pending_after_cache,
                resolved_ib_host,
                resolved_ib_port,
                resolved_ib_client_id,
            )
            pending_after_ib = []
            for ticker in pending_after_cache:
                if ticker in ib_raw:
                    normalised = _normalise(ib_raw[ticker], trade_date)
                    if normalised is not None:
                        cache.put(f"{ticker}_ohlcv_1y", normalised)
                        result[ticker] = normalised
                    else:
                        logger.warning(
                            "No data for %s from IB after normalisation — skipping to AV",
                            ticker,
                        )
                        pending_after_ib.append(ticker)
                else:
                    pending_after_ib.append(ticker)

    if not pending_after_ib:
        return result

    # ── Source 2: Alpha Vantage ───────────────────────────────────────────────
    pending_after_av: list[str] = []
    av_call_count: int = 0

    for ticker in pending_after_ib:
        if av_api_key is None:
            # No AV key configured — fall through to yfinance directly.
            pending_after_av.append(ticker)
            continue

        if av_call_count >= _AV_CALL_LIMIT:
            logger.warning(
                "Alpha Vantage near daily limit (%d/25), switching remaining tickers to yfinance",
                av_call_count,
            )
            pending_after_av.append(ticker)
            continue

        try:
            csv_str = get_stock(ticker, av_start, av_end)
            av_call_count += 1
            df_raw = _parse_av_csv(csv_str)
            if df_raw is not None:
                normalised = _normalise(df_raw, trade_date)
                if normalised is not None:
                    cache.put(f"{ticker}_ohlcv_1y", normalised)
                    result[ticker] = normalised
                    logger.info(
                        "Alpha Vantage fetch success",
                        extra={"ticker": ticker, "rows": len(normalised)},
                    )
                    continue
            # Parsed successfully but no usable rows — fall through.
            logger.warning(
                "Alpha Vantage returned no usable data for %s — falling through to yfinance",
                ticker,
            )
            pending_after_av.append(ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Alpha Vantage fetch failed for %s — falling through to yfinance",
                ticker,
                extra={"error": str(exc)},
                exc_info=True,
            )
            pending_after_av.append(ticker)

    # ── Source 3: yfinance ─────────────────────────────────────────────────────
    for ticker in pending_after_av:
        # Raises YFRateLimitExceeded if any rolling window is exhausted.
        # This propagates directly to the caller as specified.
        limiter.check_and_increment()

        try:
            df_raw: pd.DataFrame = yf_retry(
                lambda t=ticker: yf.download(t, period="1y", auto_adjust=True, progress=False)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "yfinance download failed for %s",
                ticker,
                extra={"error": str(exc)},
                exc_info=True,
            )
            continue

        if df_raw is None or df_raw.empty:
            logger.warning("No data for %s from any source — skipping", ticker)
            continue

        # yfinance may return MultiIndex columns when downloading a single
        # ticker in batch mode.  Flatten if so.
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.get_level_values(0)

        normalised = _normalise(df_raw, trade_date)
        if normalised is None:
            logger.warning("No data for %s from any source — skipping", ticker)
            continue

        cache.put(f"{ticker}_ohlcv_1y", normalised)
        result[ticker] = normalised
        logger.info(
            "yfinance fetch success",
            extra={"ticker": ticker, "rows": len(normalised)},
        )

    # ── FM-06: all tickers failed ─────────────────────────────────────────────
    if not result:
        logger.error(
            "All tickers failed OHLCV fetch",
            extra={"ticker_count": len(tickers)},
        )

    return result
