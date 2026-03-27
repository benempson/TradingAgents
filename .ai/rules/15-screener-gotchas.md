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

Valid volume field: `"dayvolume"` (NOT `"averageDailyVolume3Month"` — rejected by validator).

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

## Config Path Resolution
`screener/screener.py` resolves config via `Path(__file__).parent.parent / "config"`.
Always run the screener from the project root or via `python screener/screener.py`.
Do not move `screener/` without updating `CONFIG_DIR`.
