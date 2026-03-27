---
description: Screener module gotchas — yfinance API version, IB pacing, cache security
paths: screener/**
---

# Screener Module Gotchas

## yfinance 1.2.0 API (BREAKING CHANGE from older versions)
`yfinance.Screener` no longer exists. Use `yf.screen()` with `EquityQuery` objects:

```python
from yfinance import EquityQuery
import yfinance as yf

results = yf.screen(
    EquityQuery("and", [
        EquityQuery("eq", ["sector", "Technology"]),
        EquityQuery("gt", ["dayvolume", 500000]),
    ]),
    size=100,
    sortField="percentchange",
    sortAsc=False,
)
tickers = [item["symbol"] for item in results.get("quotes", [])]
```

Valid volume field: `"dayvolume"` (NOT `"averageDailyVolume3Month"` or `"regularMarketVolume"` — rejected by validator).

**`discovery_criteria.json` — valid EquityQuery field names** (verified against yfinance 1.2.0 validator):

| Intent | Valid field name |
|---|---|
| Daily volume | `"dayvolume"` |
| Avg daily vol (3m) | `"avgdailyvol3m"` |
| Price % change today | `"percentchange"` |
| 52-week % change | `"fiftytwowkpercentchange"` |
| Price-to-book | `"pricebookratio.quarterly"` |
| P/E ratio | `"peratio.lasttwelvemonths"` |
| Sector (EQ only) | `"sector"` |
| Industry (EQ only) | `"industry"` |

**Do NOT use** camelCase names from other yfinance APIs (e.g. `regularMarketVolume`, `priceToBook`, `fiftyTwoWeekChangePercent`) — those are ticker info fields, not screener query fields, and will raise `ValueError` from the `EquityQuery` validator.

## `discovery_criteria.json` filter dicts — conversion to EquityQuery
Filters in `config/discovery_criteria.json` are stored as plain dicts:
```json
{"operator": "GT", "operands": ["percentchange", 0]}
```
`screener/discovery.py::_run_screener` converts them to `EquityQuery` instances at runtime (lowercasing the operator). Do NOT store pre-built `EquityQuery` objects in the config.

## IB Gateway Connection Failure — Interactive Fallback (R-FETCH-11, R-UI-14)
When `IB_HOST` is set but Gateway refuses the connection, `data_fetcher.py` raises
`IBConnectionFailed` (NOT a silent `{}`). `screener.py` catches it and prompts:
`"Continue fetching with yfinance instead? [y/n]:"`. If "y", retries `fetch_ohlcv`
with `skip_ib=True`; if "n", `sys.exit(1)`. The `_skip_ib` flag is preserved across
rate-limit pause retries so the user is never re-prompted for the same run.

**Do NOT** revert `_fetch_ib_async` to return `{}` on connection error — the old
silent fallback masked IB configuration problems.

## IB Request Delay — Production vs Test
`IB_REQUEST_DELAY_S` defaults to `0.1` seconds in `data_fetcher.py` for unit-test speed.
**In production, set `IB_REQUEST_DELAY_S=10`** to respect IB's ~6 req/min pacing limit.
Failure to do so causes FM-02 (IB pacing errors) for universe sizes > 6 tickers/minute.

## Cache Key Security Constraint
Cache keys (format: `{TICKER}_ohlcv_1y`) are validated against `^[A-Za-z0-9_\-]{1,64}$`
before any filesystem operation. Do NOT modify this regex to allow dots, slashes, or
other path characters — they enable path traversal attacks against the cache directory.

## Manifest `"file"` Path Confinement
`CacheStore.get()` resolves `manifest["file"]` via `os.path.realpath()` and checks it
stays within `realpath(cache_dir) + os.sep`. Never skip this check when modifying
`CacheStore` — a tampered manifest could redirect reads to arbitrary paths.

## Running the Screener — Module Invocation Required
**Always run as a module, never as a script:**
```
# CORRECT — imports resolve as package
python -m screener.screener

# WRONG — Python treats screener.py as the 'screener' module, breaking all internal imports
python screener/screener.py
```
`screener/` must also be listed in `pyproject.toml` `[tool.setuptools.packages.find] include` alongside `tradingagents*` and `cli*`, otherwise `pip install -e .` won't register it as an importable package.

## `fetch_ohlcv` Three-Loop Ticker Lifecycle
`fetch_ohlcv` processes tickers across three sequential fallback loops (IB → AV → yfinance).
A ticker can appear in **multiple** lists:
- `pending_after_cache` → all cache misses
- `pending_after_ib` → cache misses that IB didn't return data for
- `pending_after_av` → IB+AV misses that fall through to yfinance

**Any counter or side-effect (print, increment, metric) placed at the TOP of the AV loop
will fire again in the yfinance loop for tickers that fail AV.** Always place per-ticker
side-effects either in the success branch of each source, or exclusively in the final
yfinance loop (which sees every non-IB-success, non-AV-success ticker exactly once).

## Config Path Resolution
`screener/screener.py` resolves config via `Path(__file__).parent.parent / "config"`.
Always run the screener from the project root or via `python -m screener.screener`.
Do not move `screener/` without updating `CONFIG_DIR`.
