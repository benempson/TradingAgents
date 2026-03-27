"""screener/screener.py — CLI entry point and orchestrator for the TradingAgents Technical Screener.

Coordinates the full pipeline:
  1. Config load
  2. Trade date resolution
  3. Mode selection (sector vs watchlist)
  4. Discovery or watchlist population
  5. OHLCV fetch
  6. Indicator computation
  7. Screening
  8. Results table output
  9. Optional TradingAgents deep analysis
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from screener.cache_store import CacheStore
from screener.data_fetcher import IBConnectionFailed, fetch_ohlcv
from screener.discovery import get_sector_shortlist
from screener.indicator_engine import compute_indicators
from screener.screening_engine import apply_criteria
from screener.yf_rate_limiter import YFRateLimiter, YFRateLimitExceeded

logger = logging.getLogger(__name__)

# ── config ────────────────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config(base_dir: str = ".") -> dict:
    """Load all config files from the config directory.

    Args:
        base_dir: Base directory containing the ``config/`` subdirectory.
                  Ignored when the module resolves CONFIG_DIR from ``__file__``.

    Returns:
        Dict with keys ``sectors``, ``discovery_criteria``, ``screening_criteria``,
        and ``watchlists`` (list of dicts, one per watchlist file).

    Raises:
        ValueError: When any config file contains invalid JSON.
    """
    config: dict[str, Any] = {}

    def _load_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Config file {path} is invalid JSON: {exc}") from exc

    config["sectors"] = _load_json(CONFIG_DIR / "sectors.json")

    discovery_raw = _load_json(CONFIG_DIR / "discovery_criteria.json")
    config["discovery_criteria"] = discovery_raw["criteria"]

    screening_raw = _load_json(CONFIG_DIR / "screening_criteria.json")
    config["screening_criteria"] = screening_raw["criteria"]

    watchlists_dir = CONFIG_DIR / "watchlists"
    watchlists: list[dict] = []
    for wl_file in sorted(watchlists_dir.glob("*.json")):
        watchlists.append(_load_json(wl_file))
    config["watchlists"] = watchlists

    logger.info(
        "Config loaded",
        extra={
            "sectors": len(config["sectors"]),
            "screening_criteria": len(config["screening_criteria"]),
            "watchlists": len(config["watchlists"]),
        },
    )
    return config


# ── date resolution ───────────────────────────────────────────────────────────


def resolve_trade_date(date_str: str | None) -> str:
    """Resolve and validate the trade date.

    Rolls the date back to Friday if it falls on a Saturday or Sunday.

    Args:
        date_str: Date string in ``YYYY-MM-DD`` format, or ``None`` to use today.

    Returns:
        Resolved date string in ``YYYY-MM-DD`` format.

    Side-effects:
        Prints a rollback notice when a weekend date is adjusted.
        Calls ``sys.exit(1)`` on invalid date format.
    """
    if date_str is None:
        resolved = date.today()
        orig_str = resolved.strftime("%Y-%m-%d")
    else:
        try:
            resolved = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"[Screener] Invalid date format '{date_str}'. Expected YYYY-MM-DD.")
            sys.exit(1)
        orig_str = date_str

    weekday = resolved.weekday()
    if weekday == 5:  # Saturday → subtract 1 day
        friday = resolved - timedelta(days=1)
        print(
            f"[Screener] {orig_str} is a weekend — using "
            f"{friday.strftime('%Y-%m-%d')} (most recent trading day)."
        )
        return friday.strftime("%Y-%m-%d")
    if weekday == 6:  # Sunday → subtract 2 days
        friday = resolved - timedelta(days=2)
        print(
            f"[Screener] {orig_str} is a weekend — using "
            f"{friday.strftime('%Y-%m-%d')} (most recent trading day)."
        )
        return friday.strftime("%Y-%m-%d")

    return resolved.strftime("%Y-%m-%d")


# ── TA provider resolution ────────────────────────────────────────────────────

# Models to use when the claude_code provider is selected.  These are the
# current-generation Claude models appropriate for deep analysis.
_CLAUDE_CODE_DEEP_MODEL = "claude-opus-4-6"
_CLAUDE_CODE_QUICK_MODEL = "claude-sonnet-4-6"

# Priority order for auto-detection when SCREENER_TA_PROVIDER is not set.
_PROVIDER_KEY_MAP: list[tuple[str, str]] = [
    ("OPENAI_API_KEY", "openai"),
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("GOOGLE_API_KEY", "google"),
]


def _resolve_ta_provider() -> str:
    """Determine which LLM provider to use for the TradingAgents deep analysis.

    Resolution order:
    1. ``SCREENER_TA_PROVIDER`` env var — explicit override (any supported value).
    2. ``OPENAI_API_KEY`` present → ``"openai"``.
    3. ``ANTHROPIC_API_KEY`` present → ``"anthropic"``.
    4. ``GOOGLE_API_KEY`` present → ``"google"``.
    5. Default → ``"claude_code"`` (works with Claude Max; no API key required).

    Returns:
        Provider name string compatible with ``DEFAULT_CONFIG["llm_provider"]``.
    """
    explicit = os.environ.get("SCREENER_TA_PROVIDER")
    if explicit:
        logger.info(
            "TA provider set via SCREENER_TA_PROVIDER",
            extra={"provider": explicit},
        )
        return explicit

    for env_var, provider in _PROVIDER_KEY_MAP:
        if os.environ.get(env_var):
            logger.info(
                "TA provider auto-detected from API key",
                extra={"env_var": env_var, "provider": provider},
            )
            return provider

    logger.info(
        "No API keys found — defaulting TA provider to claude_code",
    )
    return "claude_code"


# ── interactive prompts ───────────────────────────────────────────────────────


def _safe_input(prompt: str) -> str:
    """Wrap ``input()`` to handle KeyboardInterrupt gracefully."""
    try:
        return input(prompt)
    except KeyboardInterrupt:
        print()
        sys.exit(0)


def prompt_sector_mode() -> bool:
    """Ask the user whether to screen by sector or watchlist.

    Returns:
        ``True`` for sector mode, ``False`` for watchlist mode.
    """
    answer = _safe_input("Screen by sector? [y/n]: ").strip().lower()
    return answer == "y"


def prompt_sector_selection(sectors: list[dict]) -> list[dict]:
    """Present a numbered sector list and return the selected sector dicts.

    Accepts comma- or space-separated indices (1-based).

    Args:
        sectors: List of sector dicts from ``config["sectors"]``.

    Returns:
        List of selected sector dicts.

    Side-effects:
        Prints the numbered list.  Calls ``sys.exit(1)`` on invalid input.
    """
    print("\nAvailable sectors:")
    for i, s in enumerate(sectors, start=1):
        print(f"  {i}. {s['name']}")
    raw = _safe_input("\nEnter sector number(s) (comma or space separated): ").strip()

    if not raw:
        print("Invalid selection. Exiting.")
        sys.exit(1)

    # Accept both comma and space as separators.
    tokens = raw.replace(",", " ").split()
    selected: list[dict] = []
    for token in tokens:
        try:
            idx = int(token) - 1
        except ValueError:
            print("Invalid selection. Exiting.")
            sys.exit(1)
        if idx < 0 or idx >= len(sectors):
            print("Invalid selection. Exiting.")
            sys.exit(1)
        selected.append(sectors[idx])

    if not selected:
        print("Invalid selection. Exiting.")
        sys.exit(1)

    return selected


def prompt_discovery_criteria(criteria_list: list[dict]) -> dict:
    """Present a numbered discovery criteria list and return the selected entry.

    Args:
        criteria_list: List of criteria dicts from ``config["discovery_criteria"]``.

    Returns:
        Selected criteria dict.

    Side-effects:
        Prints the numbered list.  Calls ``sys.exit(1)`` on invalid input.
    """
    print("\nAvailable discovery criteria:")
    for i, c in enumerate(criteria_list, start=1):
        print(f"  {i}. {c['name']} — {c.get('description', '')}")
    raw = _safe_input("\nSelect discovery criteria number: ").strip()

    try:
        idx = int(raw) - 1
    except ValueError:
        print("Invalid selection. Exiting.")
        sys.exit(1)

    if idx < 0 or idx >= len(criteria_list):
        print("Invalid selection. Exiting.")
        sys.exit(1)

    return criteria_list[idx]


def prompt_watchlist_selection(watchlists: list[dict]) -> dict:
    """Present a numbered watchlist list and return the selected watchlist dict.

    Args:
        watchlists: List of watchlist dicts from ``config["watchlists"]``.

    Returns:
        Selected watchlist dict.

    Side-effects:
        Prints the numbered list.  Calls ``sys.exit(1)`` on invalid input.
    """
    print("\nAvailable watchlists:")
    for i, w in enumerate(watchlists, start=1):
        print(f"  {i}. {w['name']} ({len(w.get('tickers', []))} tickers)")
    raw = _safe_input("\nSelect watchlist number: ").strip()

    try:
        idx = int(raw) - 1
    except ValueError:
        print("Invalid selection. Exiting.")
        sys.exit(1)

    if idx < 0 or idx >= len(watchlists):
        print("Invalid selection. Exiting.")
        sys.exit(1)

    return watchlists[idx]


def prompt_screening_criteria(criteria_list: list[dict]) -> dict:
    """Present a numbered screening criteria list and return the selected entry.

    Args:
        criteria_list: List of criteria dicts from ``config["screening_criteria"]``.

    Returns:
        Selected criteria dict.

    Side-effects:
        Prints the numbered list.  Calls ``sys.exit(1)`` on invalid input.
    """
    print("\nAvailable screening criteria:")
    for i, c in enumerate(criteria_list, start=1):
        print(f"  {i}. {c['name']} — {c.get('description', '')}")
    raw = _safe_input("\nSelect screening criteria number: ").strip()

    try:
        idx = int(raw) - 1
    except ValueError:
        print("Invalid selection. Exiting.")
        sys.exit(1)

    if idx < 0 or idx >= len(criteria_list):
        print("Invalid selection. Exiting.")
        sys.exit(1)

    return criteria_list[idx]


# ── TA helper ─────────────────────────────────────────────────────────────────


def _run_ta_for_ticker(ta: Any, ticker: str, trade_date: str) -> dict:
    """Run TradingAgents deep analysis for a single ticker.

    Args:
        ta: TradingAgentsGraph instance with a ``propagate()`` method.
        ticker: Ticker symbol to analyse.
        trade_date: Trade date string in ``YYYY-MM-DD`` format.

    Returns:
        Result dict with keys ``ticker``, ``decision``, ``confidence``,
        ``summary``.  On ``propagate()`` failure the decision is set to
        ``"ANALYSIS FAILED"`` so that other tickers in the batch are not aborted.
    """
    try:
        result = ta.propagate(ticker, trade_date)
        return {
            "ticker": ticker,
            "decision": result.get("decision", "UNKNOWN"),
            "confidence": result.get("confidence", "N/A"),
            "summary": result.get("summary", ""),
        }
    except Exception as exc:  # noqa: BLE001 — individual ticker failures must not abort the batch
        logger.error(
            "propagate() failed",
            extra={"ticker": ticker},
            exc_info=True,
        )
        return {
            "ticker": ticker,
            "decision": "ANALYSIS FAILED",
            "confidence": "N/A",
            "summary": str(exc),
        }


# ── results table ─────────────────────────────────────────────────────────────


def _print_results_table(survivors: list[dict], top_n: int) -> None:
    """Print a fixed-width ranked results table for the top N screener survivors.

    Args:
        survivors: Sorted list of result dicts from ``apply_criteria()``.
        top_n: Maximum number of rows to display.
    """
    print()
    header = (
        f"{'Rank':>4} | {'Ticker':<6} | {'Score':>6} | {'RSI':>5} | "
        f"{'MACD Hist':>9} | {'Vol Ratio':>9} | {'ATR%':>5}"
    )
    separator = "-" * len(header)
    print(header)
    print(separator)

    for rank, result in enumerate(survivors[:top_n], start=1):
        ind = result["indicators"]
        rsi = ind.get("rsi")
        macdh = ind.get("macdh")
        vol_ratio = ind.get("vol_ratio")
        atr_pct = ind.get("atr_pct")

        rsi_str = f"{rsi:>5.1f}" if rsi is not None else "  N/A"
        macdh_str = f"{macdh:>9.3f}" if macdh is not None else "      N/A"
        vol_str = f"{vol_ratio:>9.2f}" if vol_ratio is not None else "      N/A"
        atr_str = f"{atr_pct:>5.2f}" if atr_pct is not None else "  N/A"

        print(
            f"{rank:>4} | {result['ticker']:<6} | {result['score']:>6.3f} | "
            f"{rsi_str} | {macdh_str} | {vol_str} | {atr_str}"
        )


def _print_ta_summary_table(ta_results: list[dict]) -> None:
    """Print a summary table after TradingAgents deep analysis.

    Args:
        ta_results: List of result dicts from ``_run_ta_for_ticker()``.
    """
    print()
    header = (
        f"{'Ticker':<6} | {'Score':>6} | {'RSI':>5} | "
        f"{'TA Decision':<17} | {'Confidence':<12} | Summary"
    )
    print(header)
    print("-" * max(len(header), 80))

    for r in ta_results:
        score_str = f"{r.get('score', 0.0):>6.3f}"
        rsi_val = r.get("rsi")
        rsi_str = f"{rsi_val:>5.1f}" if rsi_val is not None else "  N/A"
        decision = r.get("decision", "")[:17]
        confidence = r.get("confidence", "N/A")[:12]
        summary = r.get("summary", "")[:60]
        print(
            f"{r['ticker']:<6} | {score_str} | {rsi_str} | "
            f"{decision:<17} | {confidence:<12} | {summary}"
        )


# ── main orchestrator ─────────────────────────────────────────────────────────


def main(top_n: int = 5, date_str: str | None = None, no_ta: bool = False) -> None:
    """Run the full TradingAgents Technical Screener pipeline.

    Args:
        top_n: Maximum number of top survivors to display and optionally send
               to TradingAgents deep analysis.
        date_str: Trade date as ``YYYY-MM-DD`` string, or ``None`` to use today.
        no_ta: When ``True``, skip the TradingAgents deep-analysis step entirely.
    """
    # ── Step 1: Config load ────────────────────────────────────────────────────
    config = load_config()

    # ── Step 2: Date resolution ────────────────────────────────────────────────
    trade_date = resolve_trade_date(date_str)

    # ── Step 3: Mode selection ─────────────────────────────────────────────────
    use_sector = prompt_sector_mode()

    # ── Step 4: Discovery or watchlist population ──────────────────────────────
    cache = CacheStore()
    limiter = YFRateLimiter()

    if use_sector:
        selected_sectors = prompt_sector_selection(config["sectors"])
        discovery_criteria = prompt_discovery_criteria(config["discovery_criteria"])

        all_tickers: list[str] = []
        for sector in selected_sectors:
            print(f"[Discovery] Fetching top 100 stocks for sector: {sector['name']}...")
            sector_tickers = get_sector_shortlist(
                sector_key=sector["id"],
                yf_sector=sector["yf_sector"],
                discovery_criteria=discovery_criteria,
                limiter=limiter,
            )
            all_tickers.extend(sector_tickers)

        # Deduplicate while preserving insertion order.
        seen: set[str] = set()
        unique_tickers: list[str] = []
        duplicates = 0
        for t in all_tickers:
            if t not in seen:
                seen.add(t)
                unique_tickers.append(t)
            else:
                duplicates += 1

        print(
            f"[Discovery] Combined ticker universe: {len(unique_tickers)} tickers "
            f"({duplicates} duplicates removed)."
        )

        if not unique_tickers:
            print("No tickers found for any selected sector. Exiting.")
            sys.exit(0)

        tickers = unique_tickers

    else:
        watchlist = prompt_watchlist_selection(config["watchlists"])
        tickers = watchlist.get("tickers", [])
        print(
            f"[Screener] Using watchlist '{watchlist['name']}': {len(tickers)} tickers."
        )

    # ── Step 5: OHLCV fetch ────────────────────────────────────────────────────
    print(f"[Fetcher] Fetching OHLCV data for {len(tickers)} tickers...")
    _skip_ib = False  # set True after user acknowledges an IB connection failure
    ohlcv_data: dict = {}
    while True:
        try:
            ohlcv_data = fetch_ohlcv(tickers, cache, limiter, trade_date, skip_ib=_skip_ib)
            break  # success
        except IBConnectionFailed as exc:
            logger.warning(
                "IB Gateway unreachable — prompting user for fallback decision",
                extra={"host": exc.host, "port": exc.port},
            )
            print(f"\n[Fetcher] {exc}")
            answer = _safe_input("Continue fetching with yfinance instead? [y/n]: ").strip().lower()
            if answer != "y":
                logger.info("User chose to stop after IB connection failure")
                sys.exit(1)
            _skip_ib = True
            logger.info("User confirmed yfinance fallback; IB will be skipped for this run")
        except YFRateLimitExceeded as exc:
            logger.warning(
                "yfinance rate limit hit during OHLCV fetch",
                extra={"window": exc.window, "count": exc.count, "limit": exc.limit},
            )
            wait_secs = max(1, math.ceil((exc.reset_at - datetime.now(timezone.utc)).total_seconds()))
            while True:
                answer = _safe_input(
                    f"\n[Fetcher] yfinance {exc.window} limit reached ({exc.count}/{exc.limit}). "
                    f"[w]ait {wait_secs}s and continue / [s]top: "
                ).strip().lower()
                if answer == "w":
                    print(f"[Fetcher] Waiting {wait_secs}s for rate-limit window to reset...")
                    time.sleep(wait_secs)
                    break
                elif answer == "s":
                    logger.info("User chose to stop after yfinance rate limit")
                    sys.exit(1)
                else:
                    print(f"  Invalid input '{answer}' — enter 'w' to wait or 's' to stop.")

    if not ohlcv_data:
        print("No OHLCV data could be fetched for any ticker. Check data sources.")
        sys.exit(1)

    # ── Step 6: Indicator computation ─────────────────────────────────────────
    print(f"[Screener] Computing indicators for {len(ohlcv_data)} tickers...")
    indicators_by_ticker: dict[str, dict] = {}
    for ticker, df in ohlcv_data.items():
        ind = compute_indicators(df, ticker)
        if ind is not None:
            indicators_by_ticker[ticker] = ind
        else:
            logger.warning(
                "compute_indicators returned None for ticker — skipping",
                extra={"ticker": ticker},
            )

    # ── Step 7: Screening ──────────────────────────────────────────────────────
    screening_criteria = prompt_screening_criteria(config["screening_criteria"])
    criteria_name = screening_criteria.get("name", screening_criteria.get("id", "unknown"))
    print(f"[Screener] Applying {criteria_name} screening criteria...")

    survivors = apply_criteria(indicators_by_ticker, screening_criteria)

    if not survivors:
        print(
            f"No tickers passed the {criteria_name} screening criteria. "
            "Try a different criteria set."
        )
        sys.exit(0)

    # ── Step 8: Results table ──────────────────────────────────────────────────
    _print_results_table(survivors, top_n)

    # ── Step 9: Optional TA deep analysis ─────────────────────────────────────
    if no_ta or not survivors:
        return

    answer = _safe_input(f"\nRun TradingAgents deep analysis on top {top_n}? [y/n]: ").strip().lower()
    if answer != "y":
        return

    # Import lazily so that the screener module is importable without the full
    # tradingagents graph installed (e.g. in unit-test environments).
    try:
        from tradingagents.default_config import DEFAULT_CONFIG  # noqa: PLC0415
        from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: PLC0415
    except ImportError as exc:
        logger.error(
            "TradingAgentsGraph is not available — cannot run deep analysis",
            exc_info=True,
        )
        print(f"[TA] TradingAgents not available: {exc}")
        return

    ta_config = dict(DEFAULT_CONFIG)
    provider = _resolve_ta_provider()
    ta_config["llm_provider"] = provider
    if provider == "claude_code":
        # claude_code uses Claude Max (no API key); set appropriate model names.
        ta_config["deep_think_llm"] = _CLAUDE_CODE_DEEP_MODEL
        ta_config["quick_think_llm"] = _CLAUDE_CODE_QUICK_MODEL
    print(
        f"[TA] Using provider: {provider} "
        f"(deep: {ta_config['deep_think_llm']}, "
        f"quick: {ta_config['quick_think_llm']})"
    )
    ta = TradingAgentsGraph(config=ta_config)

    top_survivors = survivors[:top_n]
    ta_results: list[dict] = []

    for i, result in enumerate(top_survivors, start=1):
        ticker = result["ticker"]
        print(f"[TA] Analysing {ticker} ({i}/{len(top_survivors)})...")
        ta_result = _run_ta_for_ticker(ta, ticker, trade_date)
        # Carry through score and RSI from the screener result for the summary table.
        ta_result["score"] = result["score"]
        ta_result["rsi"] = result["indicators"].get("rsi")
        ta_results.append(ta_result)

    _print_ta_summary_table(ta_results)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TradingAgents Technical Screener")
    parser.add_argument(
        "--top-n",
        type=int,
        default=int(os.environ.get("SCREENER_TOP_N", "5")),
    )
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--no-ta", action="store_true")
    args = parser.parse_args()
    main(top_n=args.top_n, date_str=args.date, no_ta=args.no_ta)
