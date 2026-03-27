# Technical Screener — Operational Reference
**Spec:** docs/specs/screener/screener-spec.md
**Generated:** 2026-03-27
**Module:** screener/

---

## 1. Module Map

| Module | File | Primary export | Responsibility |
|--------|------|----------------|----------------|
| Orchestrator / CLI | `screener/screener.py` | `main()` | Coordinates all pipeline steps; provides the `argparse` CLI entry point and all interactive prompts |
| Discovery | `screener/discovery.py` | `get_sector_shortlist()` | Queries yfinance Screener API to produce a sector ticker shortlist; persists result JSON to disk |
| Data Fetcher | `screener/data_fetcher.py` | `fetch_ohlcv()` | IB Gateway → Alpha Vantage → yfinance three-source fallback chain with cache integration |
| Indicator Engine | `screener/indicator_engine.py` | `compute_indicators()` | Wraps a normalised OHLCV DataFrame with stockstats; returns a flat indicator dict for the most recent trading day |
| Screening Engine | `screener/screening_engine.py` | `apply_criteria()` | Applies hard filters then composite scoring; returns ranked survivor list |
| Cache Store | `screener/cache_store.py` | `CacheStore` class | TTL-aware Parquet cache backed by a manifest.json; atomic writes via temp-file rename |
| Rate Limiter | `screener/yf_rate_limiter.py` | `YFRateLimiter` class, `YFRateLimitExceeded` exception | Rolling-window rate limiter for yfinance calls; disk-persisted across process restarts |

---

## 2. Entry Point

```
python screener/screener.py [--top-n N] [--date YYYY-MM-DD] [--no-ta]
```

| Argument | Type | Default | Behaviour |
|----------|------|---------|-----------|
| `--top-n` | `int` | `SCREENER_TOP_N` env var or `5` | Number of top survivors displayed and optionally sent to TA deep analysis |
| `--date` | `str` | Today's date | Trade date in `YYYY-MM-DD` format. Weekend dates roll back to the prior Friday |
| `--no-ta` | flag | absent = TA prompt enabled | When present, skips the TradingAgents deep-analysis step entirely |

After argument parsing, execution continues with `main(top_n, date_str, no_ta)`. The interactive session then prompts:
1. `Screen by sector? [y/n]`
2. (Sector path) sector number(s) → discovery criteria number
3. (Watchlist path) watchlist number
4. Screening criteria number
5. (Post-results, unless `--no-ta`) `Run TradingAgents deep analysis on top N? [y/n]`

Any invalid selection calls `sys.exit(1)` with the message `Invalid selection. Exiting.`

---

## 3. System Constants & Environment Variables

| Name | Default | Used by | Purpose |
|------|---------|---------|---------|
| `SCREENER_CACHE_DIR` | `temp/screener/data_cache` | `CacheStore` | Directory for Parquet files and `manifest.json` |
| `PRICE_DATA_VALIDITY_MINS` | `480` (8 hours) | `CacheStore` | TTL threshold in minutes for cache freshness |
| `YF_LIMIT_PER_MIN` | `100` | `YFRateLimiter` | Rolling per-minute yfinance request ceiling |
| `YF_LIMIT_PER_HOUR` | `2000` | `YFRateLimiter` | Rolling per-hour yfinance request ceiling |
| `YF_LIMIT_PER_DAY` | `48000` | `YFRateLimiter` | Rolling per-day yfinance request ceiling |
| `YF_RATE_COUNTER_FILE` | `temp/screener/yf_rate_counters.json` | `YFRateLimiter` | Path for persistent window state JSON |
| `IB_HOST` | `None` (IB skipped when absent) | `data_fetcher.fetch_ohlcv()` | IB Gateway hostname or IP |
| `IB_PORT` | `4002` | `data_fetcher.fetch_ohlcv()` | IB Gateway port |
| `IB_CLIENT_ID` | `10` | `data_fetcher.fetch_ohlcv()` | IB client ID |
| `IB_REQUEST_DELAY_S` | `0.1` | `data_fetcher._fetch_ib_async()` | Inter-request sleep between IB ticker fetches (seconds); set higher in production for IB pacing safety |
| `ALPHA_VANTAGE_API_KEY` | `None` (AV skipped when absent) | `data_fetcher.fetch_ohlcv()` | Alpha Vantage API key |
| `SCREENER_TOP_N` | `5` | `screener.py` `__main__` | Default value for `--top-n` argument |

---

## 4. Config Files

| File | Format | Key fields | Loaded by |
|------|--------|------------|-----------|
| `config/sectors.json` | JSON array | `id`, `name`, `etf`, `yf_sector` | `screener.load_config()` |
| `config/discovery_criteria.json` | JSON object `{"criteria": [...]}` | `id`, `name`, `description`, `filters` (list of `{operator, operands}` objects) | `screener.load_config()` |
| `config/screening_criteria.json` | JSON object `{"criteria": [...]}` | `id`, `name`, `description`, `hard_filters` (`rsi`, `volume`, `atr_pct`), `scoring` (`w1`, `w2`, `w3`) | `screener.load_config()` |
| `config/watchlists/*.json` | JSON object per file | `id`, `name`, `description`, `tickers` (list of strings) | `screener.load_config()` (all `*.json` files under `watchlists/` loaded and sorted by filename) |

All files are loaded at startup by `load_config()`. A `json.JSONDecodeError` on any file raises `ValueError("Config file {path} is invalid JSON: {exc}")` and causes an immediate `sys.exit(1)` before any prompts are shown.

The 8 sectors currently in `config/sectors.json`:

| id | name | ETF | `yf_sector` value |
|----|------|-----|-------------------|
| `technology` | Technology | XLK | `Technology` |
| `healthcare` | Healthcare | XLV | `Healthcare` |
| `financials` | Financials | XLF | `Financial Services` |
| `energy` | Energy | XLE | `Energy` |
| `materials` | Materials | XLB | `Basic Materials` |
| `industrials` | Industrials | XLI | `Industrials` |
| `consumer_discretionary` | Consumer Discretionary | XLY | `Consumer Cyclical` |
| `communication_services` | Communication Services | XLC | `Communication Services` |

---

## 5. Data Flow

```
python screener/screener.py
         │
         ▼
[1] load_config()          — loads sectors, discovery criteria, screening criteria, watchlists
         │
         ▼
[2] resolve_trade_date()   — validates --date arg; rolls Saturday/Sunday → Friday
         │
         ▼
[3] prompt_sector_mode()   ─── Sector path ──────────────────────────────────────────────────┐
         │                                                                                    │
         │                     prompt_sector_selection()   → list of sector dicts             │
         │                     prompt_discovery_criteria() → discovery_criteria dict          │
         │                     for each sector:                                               │
         │                       get_sector_shortlist(sector_key, yf_sector,                 │
         │                                            discovery_criteria, limiter)            │
         │                         → limiter.check_and_increment()                           │
         │                         → yf.screen(EquityQuery("and", [...]))                    │
         │                         → _save_result() → temp/screener/sector_filters_*.json    │
         │                     Deduplicate; print [Discovery] Combined ticker universe        │
         │                                                                                    │
         │              ── Watchlist path ────────────────────────────────────────────────────┘
         │                     prompt_watchlist_selection() → watchlist["tickers"]
         │
         ▼
[4] fetch_ohlcv(tickers, cache, limiter, trade_date)
         │
         ├─ Source 0: CacheStore.get("{TICKER}_ohlcv_1y")  → DataFrame on hit; skip network
         ├─ Source 1: IB Gateway (_fetch_ib / _fetch_ib_async) → 1Y daily ADJUSTED_LAST bars
         │             → _normalise(df, trade_date) → CacheStore.put()
         ├─ Source 2: Alpha Vantage get_stock() → _parse_av_csv() → _normalise() → CacheStore.put()
         │             (skipped when ALPHA_VANTAGE_API_KEY absent; capped at 20 calls/run)
         └─ Source 3: yfinance yf.download() via yf_retry()
                       → limiter.check_and_increment() before each download
                       → _normalise() → CacheStore.put()
         │
         ▼
[5] for ticker, df in ohlcv_data:
         compute_indicators(df, ticker)
           → stockstats.wrap(df.copy())
           → extract rsi, macd, macds, macdh, sma_50, sma_200, atr from ss_df columns
           → compute vol_20_avg, vol_ratio, atr_pct manually
           → _detect_macdh_crossover(macdh_series)
           → return flat indicators dict  (None on stockstats failure)
         │
         ▼
[6] prompt_screening_criteria()  → screening_criteria dict
         │
         ▼
[7] apply_criteria(indicators_by_ticker, criteria)
         │
         ├─ _validate_weights(scoring)   → ValueError if w1+w2+w3 ≠ 1.0
         ├─ for each ticker:
         │    _check_trend_filter()      → close > sma_200
         │    _check_rsi_range()         → min ≤ rsi ≤ max
         │    _check_macd_setup()        → macdh > 0 OR macdh_crossed_up_3d
         │    _check_volume()            → vol_ratio ≥ min_ratio
         │    _check_atr_pct()           → min ≤ atr_pct ≤ max
         │    _compute_score()           → composite score float
         └─ sorted descending by score → list of result dicts
         │
         ▼
[8] _print_results_table(survivors, top_n)
         Rank | Ticker | Score | RSI | MACD Hist | Vol Ratio | ATR%
         │
         ▼
[9] (optional, unless --no-ta or user declines)
         for ticker in survivors[:top_n]:
           _run_ta_for_ticker(ta, ticker, trade_date)
             → ta.propagate(ticker, trade_date)
             → returns {ticker, decision, confidence, summary}  ("ANALYSIS FAILED" on exception)
         _print_ta_summary_table(ta_results)
         Ticker | Score | RSI | TA Decision | Confidence | Summary
```

---

## 6. Public API

### `screener.screener`

```python
def main(top_n: int = 5, date_str: str | None = None, no_ta: bool = False) -> None
```
Runs the full pipeline. All interactive prompts are called from within this function. `sys.exit()` is called on invalid user input or fatal errors — does not raise.

```python
def load_config(base_dir: str = ".") -> dict
```
Loads `sectors`, `discovery_criteria`, `screening_criteria`, and `watchlists` from `config/`. Raises `ValueError` on any invalid JSON file.

```python
def resolve_trade_date(date_str: str | None) -> str
```
Returns a valid `YYYY-MM-DD` string. Rolls Saturday back 1 day, Sunday back 2 days. Calls `sys.exit(1)` on invalid format.

---

### `screener.discovery`

```python
def get_sector_shortlist(
    sector_key: str,
    yf_sector: str,
    discovery_criteria: dict,
    limiter: YFRateLimiter,
    output_dir: str = "temp/screener",
) -> list[str]
```
**Parameters:**
- `sector_key` — internal identifier used in log messages and the result file
- `yf_sector` — sector label accepted by yfinance `EquityQuery` EQ filter (must match `yf_sector` in `sectors.json`)
- `discovery_criteria` — one entry from `config/discovery_criteria.json`; `filters` list is ANDed into the screener query
- `limiter` — `YFRateLimiter`; `check_and_increment()` is called before the network request
- `output_dir` — directory where the result JSON file is written

**Returns:** List of ticker symbol strings (at most 100). Returns `[]` on screener failure or zero results.

**Raises:** `YFRateLimitExceeded` (propagated from `limiter`).

**Side-effect:** Writes `{output_dir}/sector_filters_YYYYMMDD-HHMMSS.json` on success.

---

### `screener.data_fetcher`

```python
def fetch_ohlcv(
    tickers: list[str],
    cache: CacheStore,
    limiter: YFRateLimiter,
    trade_date: str,
    ib_host: str | None = None,
    ib_port: int | None = None,
    ib_client_id: int | None = None,
) -> dict[str, pd.DataFrame]
```
**Parameters:**
- `tickers` — list of ticker symbols
- `cache` — `CacheStore` for read/write; checked before any network source
- `limiter` — `YFRateLimiter`; called before each yfinance download
- `trade_date` — `YYYY-MM-DD`; rows on or after this date are stripped
- `ib_host / ib_port / ib_client_id` — IB Gateway parameters; fall back to `IB_HOST / IB_PORT / IB_CLIENT_ID` env vars, then hard defaults (`4002`, `10`). IB source skipped when `ib_host` resolves to `None`.

**Returns:** `dict[ticker → normalised OHLCV DataFrame]`. Tickers for which all sources return empty are omitted.

**Raises:** `YFRateLimitExceeded` when the yfinance rolling window is exhausted during Source 3.

---

### `screener.indicator_engine`

```python
def compute_indicators(df: pd.DataFrame, ticker: str = "UNKNOWN") -> dict | None
```
**Parameters:**
- `df` — normalised OHLCV DataFrame (columns: Date, Open, High, Low, Close, Volume; sorted ascending by Date)
- `ticker` — used in log messages only

**Returns:** Flat indicator dict (see Section 10) for the last row, or `None` if `stockstats.wrap()` raises.

---

### `screener.screening_engine`

```python
def apply_criteria(
    indicators_by_ticker: dict[str, dict],
    criteria: dict,
) -> list[dict]
```
**Parameters:**
- `indicators_by_ticker` — maps ticker → indicators dict from `compute_indicators()`
- `criteria` — one entry from `config/screening_criteria.json` (must contain `hard_filters` and `scoring`)

**Returns:** List of result dicts sorted descending by composite score:
```python
{
    "ticker": str,
    "score": float,
    "indicators": dict,
    "filter_results": dict,  # keys: trend_filter, rsi_range, macd_setup, volume, atr_pct
}
```
Returns `[]` when no tickers pass.

**Raises:** `ValueError` when `w1 + w2 + w3` deviates from `1.0` by more than `1e-6`.

---

### `screener.cache_store.CacheStore`

```python
def __init__(self, cache_dir: str | None = None, validity_mins: int | None = None)
```
Constructor arguments override env vars. Both fall back to env vars (`SCREENER_CACHE_DIR`, `PRICE_DATA_VALIDITY_MINS`), then built-in defaults.

```python
def get(self, key: str) -> pd.DataFrame | None
```
Returns the cached DataFrame if `(utcnow - fetched_at).total_seconds() / 60 < validity_mins`, otherwise `None`. Raises `ValueError` on unsafe key characters.

```python
def put(self, key: str, df: pd.DataFrame) -> None
```
Writes Parquet file and updates manifest atomically. Raises `ValueError` on unsafe key, propagates `PermissionError` / `OSError` on filesystem failure.

---

### `screener.yf_rate_limiter.YFRateLimiter`

```python
def __init__(self, counter_file: str | None = None)
```
Loads limits from env vars. Reads persisted state from `counter_file` (or `YF_RATE_COUNTER_FILE` env var).

```python
def check_and_increment(self) -> None
```
Resets any expired windows, validates all three windows atomically, increments all counters, persists state. Raises `YFRateLimitExceeded` if any window is at its limit before incrementing.

---

## 7. Cache Key Format

Format: `{TICKER}_ohlcv_1y`
Example: `AAPL_ohlcv_1y`

The key is validated against the regex `^[A-Za-z0-9_\-]{1,64}$` before any filesystem operation. This allowlist:
- Rejects path separators (`/`, `\`, `..`)
- Rejects dots (which appear in the `.parquet` suffix appended by `put()`)
- Caps key length at 64 characters

A tampered `manifest.json` pointing a key's `"file"` field to an arbitrary path is caught by a second guard in `CacheStore.get()`: the resolved `realpath` of the Parquet file must start with `realpath(cache_dir) + os.sep`. Any entry that escapes the cache directory is silently ignored with a `logger.warning`.

**Manifest schema** (`temp/screener/data_cache/manifest.json`):
```json
{
  "{TICKER}_ohlcv_1y": {
    "file": "{TICKER}_ohlcv_1y.parquet",
    "fetched_at": "2026-03-27T10:30:00+00:00"
  }
}
```

**TTL check:** `age_mins = (utcnow - fetched_at).total_seconds() / 60.0`. Cache miss when `age_mins >= validity_mins`.

---

## 8. Rate Limiter Windows

| Window | Duration | Default limit | Env var | Reset behaviour |
|--------|----------|---------------|---------|-----------------|
| `minute` | 1 minute | 100 | `YF_LIMIT_PER_MIN` | Resets to `count=0`, `window_start=now` when `now - window_start >= 1min` |
| `hour` | 1 hour | 2000 | `YF_LIMIT_PER_HOUR` | Resets to `count=0`, `window_start=now` when `now - window_start >= 1hr` |
| `day` | 1 day | 48000 | `YF_LIMIT_PER_DAY` | Resets to `count=0`, `window_start=now` when `now - window_start >= 24hr` |

All three windows are checked atomically before any counter is incremented. If any window is at its limit, `YFRateLimitExceeded(window, count, limit, reset_at)` is raised and no counter is modified.

State is persisted to `YF_RATE_COUNTER_FILE` after every successful `check_and_increment()` via an atomic temp-file rename (`{file}.tmp` → `{file}`). A `PermissionError` on save is logged as a warning but does not raise — the in-memory counts remain correct for the current process.

On load, corrupt or missing counter files result in fresh zero-count state for all windows.

---

## 9. Screening Criteria Schema

`config/screening_criteria.json` top-level schema:
```json
{
  "criteria": [
    {
      "id": "string (unique)",
      "name": "string",
      "description": "string",
      "hard_filters": {
        "rsi":     { "min": float, "max": float },
        "volume":  { "min_ratio": float },
        "atr_pct": { "min": float, "max": float }
      },
      "scoring": {
        "w1": float,
        "w2": float,
        "w3": float
      }
    }
  ]
}
```

**Weight validation rule:** `abs(w1 + w2 + w3 - 1.0) < 1e-6`. Validated by `_validate_weights()` at the start of every `apply_criteria()` call. Raises `ValueError` immediately — no ticker data is processed if weights are invalid.

**Currently defined criteria:**

| id | RSI range | Vol ratio min | ATR% range | w1 / w2 / w3 |
|----|-----------|---------------|------------|---------------|
| `default` | [40, 70] | 1.2 | [0.5, 6.0] | 0.4 / 0.4 / 0.2 |
| `aggressive` | [50, 80] | 1.5 | [1.0, 8.0] | 0.3 / 0.5 / 0.2 |
| `conservative` | [35, 60] | 1.1 | [0.3, 4.0] | 0.5 / 0.3 / 0.2 |

---

## 10. Indicator Fields

All fields are for the **most recent trading day** in the input DataFrame.

| Field | Type | Computation | None conditions |
|-------|------|-------------|-----------------|
| `close` | `float` | `df["Close"].iloc[-1]` | Never None (required for all downstream logic) |
| `sma_50` | `float \| None` | `stockstats["close_50_sma"].iloc[-1]` | `df` has fewer than 50 rows, or NaN at last position |
| `sma_200` | `float \| None` | `stockstats["close_200_sma"].iloc[-1]` | `df` has fewer than 200 rows, or NaN at last position |
| `rsi` | `float \| None` | `stockstats["rsi"].iloc[-1]` (RSI-14) | Fewer than ~15 rows of data |
| `macd` | `float \| None` | `stockstats["macd"].iloc[-1]` | Insufficient history for EMA-12/26 |
| `macds` | `float \| None` | `stockstats["macds"].iloc[-1]` (signal line, EMA-9 of MACD) | Insufficient history |
| `macdh` | `float \| None` | `stockstats["macdh"].iloc[-1]` (MACD histogram = macd − macds) | Insufficient history |
| `macdh_crossed_up_3d` | `bool` | `True` if any consecutive pair in the last 3 non-NaN macdh values transitions from `< 0` to `>= 0` | Always returns `False` (not None) on insufficient data |
| `macdh_series` | `list[float]` | All non-NaN values from the full `macdh` series (used by scoring engine for hist_min/hist_max normalisation) | Empty list on insufficient history |
| `atr` | `float \| None` | `stockstats["atr"].iloc[-1]` (ATR-14) | Fewer than ~15 rows of data |
| `atr_pct` | `float \| None` | `(atr / close) * 100.0` | `atr` is None, or `close <= 0` |
| `volume` | `float` | `df["Volume"].iloc[-1]` | Never None |
| `vol_20_avg` | `float \| None` | `df["Volume"].rolling(20).mean().iloc[-1]` | Fewer than 20 rows, or rolling mean is NaN or zero |
| `vol_ratio` | `float \| None` | `volume / vol_20_avg` | `vol_20_avg` is None or zero |

**Hard filter disqualification:** A `None` value on any of the following fields causes automatic disqualification (the relevant filter check returns `False`): `close`, `sma_200` (trend filter), `rsi` (RSI range), `macdh` (MACD setup, unless `macdh_crossed_up_3d` is `True`), `vol_ratio` (volume filter), `atr_pct` (ATR% filter).

---

## 11. Failure Modes Quick Reference

| FM | Trigger | Module | Response |
|----|---------|--------|----------|
| FM-01 | IB Gateway connection refused or timed out | `data_fetcher` | `logger.warning`; return `{}`; all tickers fall through to AV/yfinance |
| FM-02 | IB pacing error / error bars for a single ticker | `data_fetcher._fetch_ib_async` | `logger.warning` for that ticker; ticker falls through to AV/yfinance |
| FM-03 | `YFRateLimitExceeded` raised | `yf_rate_limiter` | `logger.error`; exception propagates to `screener.main()`; `sys.exit(1)` |
| FM-04 | Alpha Vantage call count reaches 20 in a single run | `data_fetcher` | `logger.warning`; remaining tickers switched to yfinance; no exception |
| FM-05 | Discovery returns 0 tickers for a sector | `discovery` | `logger.warning`; returns `[]`; if all sectors empty, `sys.exit(0)` |
| FM-06 | All tickers fail OHLCV fetch from all sources | `data_fetcher` | `logger.error`; `screener.main()` prints message and calls `sys.exit(1)` |
| FM-07 | No tickers pass hard filters | `screening_engine` | Returns `[]`; `screener.main()` prints message and calls `sys.exit(0)` |
| FM-08 | `ta.propagate()` raises for a ticker | `screener.main()` | `logger.error`; row marked `"ANALYSIS FAILED"`; next ticker continues |
| FM-09 | Config file contains invalid JSON | `screener.load_config()` | Raises `ValueError`; `sys.exit(1)` before any prompts |
| FM-10 | Cache directory not writable | `cache_store` | `logger.error`; `PermissionError` / `OSError` propagated to caller |
| FM-11 | `stockstats.wrap()` raises during indicator computation | `indicator_engine` | `logger.error`; returns `None`; ticker excluded from screening |
| FM-12 | `--date` resolves to Saturday or Sunday | `screener.resolve_trade_date()` | Rolls back to most recent Friday; prints notice; not an error |

---

## 12. Edge Cases

**Weekend date rollback (`resolve_trade_date`)**
Saturday (`weekday() == 5`) rolls back by 1 day; Sunday (`weekday() == 6`) rolls back by 2 days. The rollback is applied to both `--date` arguments and the default `date.today()`. The effective date is printed to stdout: `[Screener] {orig_date} is a weekend — using {friday} (most recent trading day).`

**IB pacing — `IB_REQUEST_DELAY_S` default is 0.1s in code, 10s in spec**
The spec describes a 10-second inter-request sleep for IB production use. The implementation defaults `IB_REQUEST_DELAY_S` to `0.1` for unit-test speed and relies on the operator setting this env var to `10` (or higher) in production. Failure to do so will trigger IB pacing errors (FM-02) for large ticker universes.

**Alpha Vantage 20-call switch**
The `_AV_CALL_LIMIT` constant is `20` (not 25). The AV free tier allows 25 daily calls; the 5-call buffer is intentional. When the within-run count reaches 20, all remaining tickers for that `fetch_ohlcv()` call are sent to yfinance. The count resets on the next call to `fetch_ohlcv()` (it is a local variable, not persisted).

**Path traversal guard in cache**
Two layers of protection exist. First, `CacheStore._validate_key()` rejects any key not matching `^[A-Za-z0-9_\-]{1,64}$`. Second, `CacheStore.get()` resolves the manifest `"file"` field via `os.path.realpath()` and confirms the result starts with `realpath(cache_dir) + os.sep` before opening the file. An attacker who edits `manifest.json` to point `"file"` at `../../../../etc/passwd` will receive a `logger.warning` and a `None` return, not a file read.

**`ib_async` optional dependency**
If `ib_async` is not installed, the `from ib_async import ...` at module level sets `IB = None`. `fetch_ohlcv()` checks `IB is None` and logs a warning before skipping the IB source entirely, without raising an exception.

**Multi-sector deduplication**
When multiple sectors are selected, tickers are merged in insertion order. Duplicates are tracked with a counter and printed: `[Discovery] Combined ticker universe: {n} tickers ({k} duplicates removed).` If the deduplicated list is empty, `sys.exit(0)` is called.

**MACD histogram crossover lookback**
`_detect_macdh_crossover()` operates on `macdh_series.dropna().values`. The `lookback` parameter (default `3`) determines how many of the last values to inspect. If fewer than 2 non-NaN values exist, `False` is returned. Crossover detection is based on consecutive pairs within the final `lookback` positions, not absolute row indices of the original DataFrame.

**Composite score MACD component guard**
When all values in `macdh_series` are identical (`hist_max == hist_min`), the MACD normalisation would divide by zero. The implementation substitutes `macdh_component = 0.5` (neutral) in this case.

**yfinance MultiIndex columns**
When `yf.download()` is called for a single ticker in certain yfinance versions, it may return a `pd.MultiIndex` column set. `data_fetcher` flattens this with `df.columns.get_level_values(0)` before passing to `_normalise()`.
