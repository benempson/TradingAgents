"""Sector discovery module — queries yfinance Screener to produce a shortlist of tickers.

Responsibility: Given a sector key and discovery criteria, return up to 100 ticker
symbols that satisfy volume and sector filters. Persists the raw result to disk for
audit and downstream caching.

yfinance API used: ``yf.screen(EquityQuery(...), size=100, ...)`` — requires yfinance ≥ 1.2.0.
"""

import datetime
import json
import logging
import os
from typing import Any

import yfinance as yf
from yfinance import EquityQuery

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

_MAX_RESULTS = 100
_MIN_VOLUME = 500_000
_RESULT_FILE_PREFIX = "sector_filters_"
_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


# ── public API ────────────────────────────────────────────────────────────────

def get_sector_shortlist(
    sector_key: str,
    yf_sector: str,
    discovery_criteria: dict,
    limiter: Any,
    output_dir: str = "temp/screener",
) -> list[str]:
    """Return up to 100 ticker symbols for the given sector using yfinance Screener.

    Args:
        sector_key: Internal identifier for the sector (used in the result file and logs).
        yf_sector: Sector string accepted by yfinance EquityQuery's EQ filter
                   (e.g. "Technology", "Healthcare"). Must be one of the values in
                   ``EQUITY_SCREENER_EQ_MAP["sector"]``.
        discovery_criteria: Dict with at least an "id" key and a "filters" list.
                            Extra ``EquityQuery`` operands from
                            ``discovery_criteria["filters"]`` are appended to the
                            screener query's AND clause.
        limiter: YFRateLimiter instance. ``check_and_increment()`` is called before
                 any yfinance network activity.
        output_dir: Directory path where the JSON result file is written.

    Returns:
        A list of ticker symbol strings (at most 100), or an empty list on failure.
    """
    logger.info("Starting discovery for sector %s", sector_key)

    criteria_id: str = discovery_criteria.get("id", "unknown")
    extra_filters: list = discovery_criteria.get("filters", [])

    # Rate-limit gate — must fire before any yfinance call.
    limiter.check_and_increment()

    try:
        tickers = _run_screener(yf_sector, extra_filters)
    except Exception:
        logger.error(
            "Discovery API call failed",
            extra={"sector": sector_key},
            exc_info=True,
        )
        return []

    # Safety cap — enforced even if the upstream library respects size=_MAX_RESULTS.
    tickers = tickers[:_MAX_RESULTS]

    if not tickers:
        logger.warning(
            "No tickers found",
            extra={"sector": sector_key, "criteria_id": criteria_id},
        )
        return []

    logger.info("Discovery complete: %d tickers found for %s", len(tickers), sector_key)

    _save_result(output_dir, sector_key, criteria_id, tickers)

    return tickers


# ── internal helpers ──────────────────────────────────────────────────────────

def _run_screener(yf_sector: str, extra_filters: list) -> list[str]:
    """Execute the yfinance screen query and return raw ticker symbols.

    Constructs an AND query combining a minimum daily-volume filter, a sector
    equality filter, and any caller-supplied extra EquityQuery operands.

    Args:
        yf_sector: Sector label for the EQ filter (e.g. "Technology").
        extra_filters: Additional ``EquityQuery`` objects to AND into the query.

    Returns:
        List of ticker symbol strings from the API response.
    """
    base_operands: list[EquityQuery] = [
        EquityQuery("gt", ["dayvolume", _MIN_VOLUME]),
        EquityQuery("eq", ["sector", yf_sector]),
    ]
    # discovery_criteria.json stores filters as plain dicts; convert them here.
    # EquityQuery instances passed directly (e.g. from tests) are kept as-is.
    for f in extra_filters:
        if isinstance(f, dict):
            base_operands.append(EquityQuery(f["operator"].lower(), f["operands"]))
        else:
            base_operands.append(f)

    query = EquityQuery("and", base_operands)

    response: dict = yf.screen(
        query,
        size=_MAX_RESULTS,
        sortField="percentchange",
        sortAsc=False,
    )

    return [item["symbol"] for item in response.get("quotes", [])]


def _save_result(
    output_dir: str,
    sector_key: str,
    criteria_id: str,
    tickers: list[str],
) -> None:
    """Persist the discovery result to a timestamped JSON file.

    Args:
        output_dir: Target directory (created if absent).
        sector_key: Internal sector identifier stored in the file.
        criteria_id: Discovery criteria identifier stored in the file.
        tickers: The ticker list to persist.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    filename = f"{_RESULT_FILE_PREFIX}{timestamp.strftime(_TIMESTAMP_FORMAT)}.json"
    filepath = os.path.join(output_dir, filename)

    payload = {
        "sector_key": sector_key,
        "discovery_criteria_id": criteria_id,
        "run_at": timestamp.isoformat(),
        "ticker_count": len(tickers),
        "tickers": tickers,
    }

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    logger.info("Saved discovery result to %s", filepath)
