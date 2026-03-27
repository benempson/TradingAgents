# Technical Screener — Feature Specification
**Status:** DRAFT
**Created:** 2026-03-27
**Area:** `screener/` (standalone module, sits alongside `tradingagents/`)

---

## 1. Context & Goal

`TradingAgentsGraph.propagate(ticker, date)` is an LLM-heavy operation. Running it across a large ticker universe without pre-filtering is impractical in terms of time and cost. This feature adds a two-stage pre-filter CLI tool that identifies technically interesting candidates before committing them to deep LLM analysis.

The screener has two entry modes:
- **Sector mode** — uses the Yahoo Finance Screener API to dynamically discover tradeable tickers within one or more sectors, based on configurable discovery criteria.
- **Watchlist mode** — uses a hand-curated JSON ticker list, skipping the discovery step.

Both modes then run the same technical screening pipeline (OHLCV fetch → indicators → hard filter → composite score) before optionally handing survivors to `ta.propagate()`.

**Architectural note:** The screener is a **standalone module** (`screener/`) that imports from `tradingagents/` read-only. It does not modify, extend, or inject into any of the existing layers (`dataflows/`, `agents/`, `llm_clients/`, `graph/`). Layer separation is not violated.

---

## 2. Requirements

### 2.1 CLI & UI

- [ ] **R-UI-01** The screener is invoked as `python screener/screener.py` with optional arguments: `--top-n N`, `--date YYYY-MM-DD`, `--no-ta`
- [ ] **R-UI-02** At startup, the user is prompted: `Screen by sector? [y/n]`
- [ ] **R-UI-03 (Sector path)** The screener presents a numbered list of sectors from `config/sectors.json`. The user enters one or more sector numbers (comma or space-separated, e.g. `1,3`). Any invalid entry (non-numeric, out-of-range, or empty) exits with code 1 and the message `Invalid selection. Exiting.`
- [ ] **R-UI-04 (Sector path)** After sector selection, the screener presents a numbered list of discovery criteria from `config/discovery_criteria.json`. The user selects one. Invalid entry → exit(1).
- [ ] **R-UI-05 (Watchlist path)** When sector mode is declined, a numbered list of watchlists from `config/watchlists/*.json` is presented. The user selects one. Invalid entry → exit(1). Watchlists skip the discovery step entirely.
- [ ] **R-UI-06** After sector or watchlist selection, the screener presents a numbered list of screening criteria from `config/screening_criteria.json`. The user selects one. Invalid entry → exit(1).
- [ ] **R-UI-07** `--date` defaults to today. If today is Saturday, the date rolls back to the previous Friday. If today is Sunday, it rolls back to the previous Friday.
- [ ] **R-UI-08** Progress is printed to stdout with bracketed module prefixes: `[Discovery]`, `[Fetcher]`, `[Screener]`, `[TA]`. No `print()` debug statements; all production output via `logger` or direct `sys.stdout.write`.
- [ ] **R-UI-09** The screener results are printed as a ranked table: `Rank | Ticker | Score | RSI | MACD Hist | Vol Ratio | ATR%`
- [ ] **R-UI-10** If the `--no-ta` flag is absent and survivors exist, the user is prompted: `Run TradingAgents deep analysis on top N? [y/n]`. If accepted, `ta.propagate()` runs sequentially on each candidate with a `[TA] Analysing {ticker} ({i}/{n})...` progress line.
- [ ] **R-UI-11** A final summary table is printed after the TA step: `Ticker | Score | RSI | TA Decision | Confidence | Summary`

### 2.2 Discovery Module (`discovery.py`)

- [ ] **R-DISC-01** `get_sector_shortlist(sector_key, discovery_criteria_id, limiter) -> list[str]` queries `yfinance.Screener` with: 3-month average volume > 500,000 (always applied), sector matches `yf_sector` from `sectors.json`, plus any additional filters from the selected discovery criteria.
- [ ] **R-DISC-02** Results are capped at 100 tickers per sector per call (`size=100` in query body).
- [ ] **R-DISC-03** If the screener returns 0 tickers, log `WARNING|DISCOVERY|No tickers found for {sector_key}` and return `[]`. The orchestrator continues with any tickers found from other sectors.
- [ ] **R-DISC-04** Each discovery run is saved to `temp/screener/sector_filters_YYYYMMDD-HHMMSS.json` containing: `sector_key`, `discovery_criteria_id`, `run_at` (UTC ISO), `ticker_count`, `tickers`.
- [ ] **R-DISC-05** When multiple sectors are selected, results are merged into a single deduplicated ticker list before proceeding. Duplicates are logged: `[Discovery] Combined ticker universe: {n} tickers ({k} duplicates removed)`.
- [ ] **R-DISC-06** `sectors.json` stores only metadata (id, name, etf, yf_sector) — no tickers.

### 2.3 yfinance Rate Limiter (`yf_rate_limiter.py`)

- [ ] **R-RATE-01** All yfinance calls in `discovery.py` and `data_fetcher.py` must call `limiter.check_and_increment()` before making the request.
- [ ] **R-RATE-02** Three rolling windows are enforced: per-minute (default 100), per-hour (default 2000), per-day (default 48000). Limits are read from env vars `YF_LIMIT_PER_MIN`, `YF_LIMIT_PER_HOUR`, `YF_LIMIT_PER_DAY`.
- [ ] **R-RATE-03** Window state is persisted to `YF_RATE_COUNTER_FILE` (default `temp/screener/yf_rate_counters.json`) and loaded on each run. This ensures counts are accurate across process restarts within the same window.
- [ ] **R-RATE-04** If any window is at its limit, `check_and_increment()` raises `YFRateLimitExceeded(window, count, limit)` with a message indicating which window is exhausted and how long until it resets.
- [ ] **R-RATE-05** Windows reset automatically when `now - window_start >= window_duration`.

### 2.4 OHLCV Data Fetcher (`data_fetcher.py`)

- [ ] **R-FETCH-01** `fetch_ohlcv(tickers, cache, limiter) -> dict[str, pd.DataFrame]` implements a three-source fallback chain: IB Gateway → Alpha Vantage → yfinance.
- [ ] **R-FETCH-02** All sources produce a normalised DataFrame with columns `Date` (datetime64), `Open`, `High`, `Low`, `Close`, `Volume` (float64), sorted ascending by Date, with no NaN in Close, and with no rows where `Date.date() >= today` (no partial current-day bars).
- [ ] **R-FETCH-03 (IB)** Uses `ib_async`: connects to `IB_HOST:IB_PORT` with `IB_CLIENT_ID`. Fetches 1Y daily adjusted bars (`durationStr='1 Y'`, `barSizeSetting='1 day'`, `whatToShow='ADJUSTED_LAST'`, `useRTH=True`). Applies `asyncio.sleep(10)` between requests to respect IB pacing limits (~6 req/min). Disconnects cleanly after all requests complete or on error.
- [ ] **R-FETCH-04 (IB fallback)** On `ConnectionRefusedError`, `asyncio.TimeoutError`, or any IB connect failure: print `[Fetcher] IB Gateway not reachable on {IB_HOST}:{IB_PORT}. Falling back to Alpha Vantage / yfinance.` and return `{}` — all tickers then fall through to Source 2.
- [ ] **R-FETCH-05 (Alpha Vantage)** Reuses `get_stock()` from `tradingagents/dataflows/alpha_vantage_stock.py`. Called for tickers IB did not return data for, or for all tickers if IB Gateway is not available. Tracks per-run call count; if count >= 20 (buffer before 25-call daily limit), switches remaining tickers to yfinance and logs `WARNING|FETCHER|Alpha Vantage near daily limit ({count}/25), switching remaining tickers to yfinance`.
- [ ] **R-FETCH-06 (yfinance)** Reuses `yf_retry` from `tradingagents/dataflows/stockstats_utils.py`. Calls `limiter.check_and_increment()` before each download. Last-resort fallback.
- [ ] **R-FETCH-07 (Cache)** Before attempting any source, checks `CacheStore.get(cache_key)`. If valid cache hit (age < `PRICE_DATA_VALIDITY_MINS`), uses cached data and skips all sources for that ticker.
- [ ] **R-FETCH-08 (Cache write)** Successful fetches from any source are written to cache immediately via `CacheStore.put()`.
- [ ] **R-FETCH-09 (Empty data)** If all three sources return empty/None for a ticker, log `WARNING|FETCHER|No data for {ticker} from any source — skipping` and exclude from the results dict.

### 2.5 Cache Store (`cache_store.py`)

- [ ] **R-CACHE-01** OHLCV DataFrames are stored as Parquet files in `SCREENER_CACHE_DIR` (default `temp/screener/data_cache/`).
- [ ] **R-CACHE-02** A `manifest.json` in the same directory tracks `{ cache_key: { "file": filename, "fetched_at": UTC ISO string } }`.
- [ ] **R-CACHE-03** `get(key)` returns the DataFrame if the file exists and `(utcnow - fetched_at).total_minutes() < PRICE_DATA_VALIDITY_MINS`, else returns `None`.
- [ ] **R-CACHE-04** `put(key, df)` writes the Parquet file and updates the manifest atomically (write to temp file, rename).
- [ ] **R-CACHE-05** Cache key format: `{TICKER}_ohlcv_1y` (e.g. `AAPL_ohlcv_1y`).

### 2.6 Indicator Engine (`indicator_engine.py`)

- [ ] **R-IND-01** `compute_indicators(df) -> dict | None` takes a normalised OHLCV DataFrame and returns a dict of the most recent trading day's indicator values.
- [ ] **R-IND-02** Indicators computed via `stockstats.wrap(df)` (already a project dependency): `rsi` (RSI-14), `macd` (MACD line), `macds` (signal), `macdh` (histogram), `close_50_sma` (SMA-50), `close_200_sma` (SMA-200), `atr` (ATR-14).
- [ ] **R-IND-03** Indicators computed manually from the DataFrame: `vol_20_avg` = `Volume.rolling(20).mean().iloc[-1]`, `vol_ratio` = `Volume.iloc[-1] / vol_20_avg`, `atr_pct` = `atr / Close.iloc[-1] * 100`.
- [ ] **R-IND-04** `macdh_crossed_up_3d` = `True` if the MACD histogram crossed from negative to positive within the last 3 rows. Implementation: check `macdh.iloc[i-1] < 0 and macdh.iloc[i] >= 0` for i in `[-3, -2, -1]`.
- [ ] **R-IND-05** If insufficient data exists for any indicator (e.g. < 200 rows for SMA-200, or < 20 rows for volume average), return `None` for that specific field only. The screening engine treats `None` on any required hard-filter field as automatic disqualification.
- [ ] **R-IND-06** If `stockstats.wrap()` raises an exception (e.g. malformed DataFrame), log `ERROR|INDICATOR|Failed to compute indicators for {ticker}: {exc}` and return `None` for the whole dict — the ticker is excluded from screening.

**Return dict fields:**
```python
{
    "close": float, "sma_50": float, "sma_200": float,
    "rsi": float, "macd": float, "macds": float,
    "macdh": float, "macdh_crossed_up_3d": bool,
    "atr": float, "atr_pct": float,
    "volume": float, "vol_20_avg": float, "vol_ratio": float,
}
```

### 2.7 Screening Engine (`screening_engine.py`)

- [ ] **R-SCREEN-01** `apply_criteria(indicators_by_ticker, criteria) -> list[dict]` applies hard filters then scores survivors. Returns a list sorted descending by composite score.
- [ ] **R-SCREEN-02** Hard filters (all must pass for a ticker to survive):

| Filter | Logic |
|--------|-------|
| `trend_filter` | `close > sma_200` |
| `rsi_range` | `criteria.min <= rsi <= criteria.max` |
| `macd_setup` | `macdh > 0 OR macdh_crossed_up_3d == True` |
| `volume` | `vol_ratio >= criteria.value` |
| `atr_pct` | `criteria.min_atr_pct <= atr_pct <= criteria.max_atr_pct` |

- [ ] **R-SCREEN-03** Composite score formula:
  ```
  score = w1 * (1 - abs(rsi - 50) / 50)
        + w2 * (macdh - hist_min) / (hist_max - hist_min)
        + w3 * min(vol_ratio, 3.0) / 3.0
  ```
  Where `hist_min`/`hist_max` are computed over the ticker's own full 1Y `macdh` series (passed alongside the current indicators dict). Weights `w1`, `w2`, `w3` come from the criteria JSON and must sum to 1.0.
- [ ] **R-SCREEN-04** Each result dict contains: `ticker`, `score`, `indicators` (the full indicators dict), `filter_results` (dict of which filters passed/failed, for debugging).

### 2.8 Config Files

- [ ] **R-CFG-01** `config/sectors.json` — array of sector objects: `{ id, name, etf, yf_sector }`. No ticker data.
- [ ] **R-CFG-02** `config/discovery_criteria.json` — single file: `{ "criteria": [ { id, name, description, filters: [...] } ] }`.
- [ ] **R-CFG-03** `config/screening_criteria.json` — single file: `{ "criteria": [ { id, name, description, hard_filters: {...}, scoring: {...} } ] }`.
- [ ] **R-CFG-04** `config/watchlists/*.json` — one file per watchlist: `{ id, name, description, tickers: [...] }`.
- [ ] **R-CFG-05** All config files are loaded at startup. If any file fails JSON parsing, raise `ValueError` with message `Config file {path} is invalid JSON: {exc}` and exit immediately — do not attempt to run with partial config.

---

## 3. Architecture Plan

### Compliance Check: AGENTS.md

- **Layer separation:** `screener/` is a new top-level module. It imports from `tradingagents/` but is not imported by any `tradingagents/` layer. No violation.
- **No God Module:** Each `screener/` file has exactly one responsibility. `screener.py` is the orchestrator; it delegates all logic to the other modules.
- **Subprocess safety:** No `subprocess` calls in the screener itself. `ta.propagate()` internally uses subprocess (the claude_code shim) but that is already compliant.
- **No hardcoded credentials:** All API keys and connection details come from env vars.
- **Logging:** `logging` module with named loggers per module. No `print()` in production code.

### New files (all created fresh, no existing files modified)

```
screener/
  __init__.py              # empty
  screener.py              # CLI entry point + orchestrator
  discovery.py             # yfinance.Screener → sector shortlist
  yf_rate_limiter.py       # disk-persisted rolling rate counter
  data_fetcher.py          # IB → AV → yfinance fallback chain
  indicator_engine.py      # stockstats indicator computation
  screening_engine.py      # hard filter + composite score
  cache_store.py           # TTL-aware Parquet cache

config/
  sectors.json
  discovery_criteria.json
  screening_criteria.json
  watchlists/
    mining_oil.json
    technology.json
    financials.json
    energy.json
```

### Read-only imports from existing codebase

| Import | Source |
|--------|--------|
| `yf_retry` | `tradingagents/dataflows/stockstats_utils.py` |
| `get_stock()` | `tradingagents/dataflows/alpha_vantage_stock.py` |
| `TradingAgentsGraph` | `tradingagents/graph/trading_graph.py` |
| `DEFAULT_CONFIG` | `tradingagents/default_config.py` |

### New dependency

- `ib_async` — `pip install ib_async` (must be added to `pyproject.toml` optional dependencies or a `requirements-screener.txt`)

### Environment variables added to `.env`

```
IB_HOST=127.0.0.1
IB_PORT=4002
IB_CLIENT_ID=10
SCREENER_TOP_N=5
SCREENER_CACHE_DIR=temp/screener/data_cache
YF_LIMIT_PER_MIN=100
YF_LIMIT_PER_HOUR=2000
YF_LIMIT_PER_DAY=48000
YF_RATE_COUNTER_FILE=temp/screener/yf_rate_counters.json
```

---

## 4. Data Validation

- **User input at prompts:** All prompt responses are validated before use. Non-numeric or out-of-range selections exit with code 1. Sector input supports comma/space-separated multi-value; each value is validated individually.
- **Config JSON:** Validated at startup (R-CFG-05). Schema conformance is checked by field presence; missing required fields raise `KeyError` wrapped in a clear `ValueError`.
- **OHLCV normalisation:** All price columns are coerced to float64 via `pd.to_numeric(errors='coerce')`. Rows with NaN Close are dropped. Rows where `Date.date() >= today` are dropped. Empty DataFrame after normalisation → treated as fetch failure (R-FETCH-09).
- **Indicator fields:** Any `None` indicator value on a required hard-filter field disqualifies the ticker (R-IND-05). This guards against tickers with insufficient history (e.g. recently listed stocks).
- **Screening criteria weights:** The implementation validates that `w1 + w2 + w3 == 1.0` (within float tolerance) on load, raising `ValueError` if not.
- **Date input (`--date`):** Validated as `YYYY-MM-DD` format via `datetime.strptime`. Invalid format raises `ValueError` with a clear message before any network calls.

---

## 5. Failure Modes

### FM-01: IB Gateway not reachable
- **Trigger:** `ConnectionRefusedError` or `asyncio.TimeoutError` on `ib.connectAsync()`
- **Response:** Log `WARNING|FETCHER|IB Gateway not reachable on {host}:{port}`. Print user-facing message. Return `{}` — all tickers fall through to Alpha Vantage then yfinance.
- **Log:** `logger.warning("IB Gateway not reachable", extra={"host": IB_HOST, "port": IB_PORT})`

### FM-02: IB pacing violation (IB returns error for a specific ticker)
- **Trigger:** IB returns an error bar or pacing exception for a single ticker despite `asyncio.sleep(10)`
- **Response:** Log `WARNING|FETCHER|IB pacing error for {ticker}, falling back to yfinance`. Exclude ticker from IB results — it falls through to AV/yfinance.
- **Log:** `logger.warning("IB pacing error", extra={"ticker": ticker, "error": str(exc)})`

### FM-03: yfinance rate limit exceeded
- **Trigger:** `YFRateLimiter.check_and_increment()` raises `YFRateLimitExceeded`
- **Response:** Log `ERROR|RATE|yfinance {window} limit reached ({count}/{limit}). Retry after {reset_time}.` Print user-facing message indicating the window and reset time. Raise to caller — the screener exits gracefully with code 1.
- **Log:** `logger.error("yfinance rate limit reached", extra={"window": window, "count": count, "limit": limit})`

### FM-04: Alpha Vantage daily limit approaching
- **Trigger:** AV call count within the fetcher reaches >= 20 in a single run
- **Response:** Switch all remaining tickers to yfinance. Log `WARNING|FETCHER|Alpha Vantage near daily limit, switching to yfinance`.
- **No exception raised** — degraded mode continues silently.

### FM-05: Discovery returns 0 tickers for a sector
- **Trigger:** `yfinance.Screener` returns empty results for a `yf_sector`
- **Response:** Log `WARNING|DISCOVERY|No tickers found for {sector_key}`. Return `[]` for that sector. If all selected sectors return empty, print `No tickers found for any selected sector. Exiting.` and exit with code 0.
- **Log:** `logger.warning("No tickers found", extra={"sector": sector_key, "criteria": discovery_criteria_id})`

### FM-06: All tickers fail OHLCV fetch
- **Trigger:** Every ticker in the universe returns empty from all three sources
- **Response:** Print `No OHLCV data could be fetched for any ticker. Check data sources.` Exit with code 1.
- **Log:** `logger.error("All tickers failed OHLCV fetch", extra={"ticker_count": len(tickers)})`

### FM-07: Zero tickers pass screening filters
- **Trigger:** `apply_criteria()` returns an empty list
- **Response:** Print `No tickers passed the [criteria name] screening criteria. Try a different criteria set.` Exit with code 0 (not an error — valid outcome).
- **Log:** `logger.info("No tickers passed screening", extra={"criteria": criteria_id, "input_count": n})`

### FM-08: `ta.propagate()` raises an exception for a ticker
- **Trigger:** Any exception thrown by `TradingAgentsGraph.propagate()` for a specific ticker during the deep analysis step
- **Response:** Log `ERROR|TA|propagate() failed for {ticker}: {exc}`. Mark the ticker's row in the final summary as `TA Decision: ANALYSIS FAILED`. Continue to the next ticker — do not abort the batch.
- **Log:** `logger.error("propagate() failed", extra={"ticker": ticker}, exc_info=True)`

### FM-09: Config file invalid JSON
- **Trigger:** `json.loads()` raises `json.JSONDecodeError` when loading any config file at startup
- **Response:** Raise `ValueError(f"Config file {path} is invalid JSON: {exc}")`. Print to stderr and exit with code 1 before any prompts.

### FM-10: Cache directory not writable
- **Trigger:** `os.makedirs()` or Parquet write raises `PermissionError` or `OSError`
- **Response:** Log `ERROR|CACHE|Cache directory {path} is not writable: {exc}`. Print `[Screener] Cannot write to cache directory {path}. Check permissions and SCREENER_CACHE_DIR setting.` Exit with code 1.
- **Log:** `logger.error("Cache directory not writable", extra={"path": cache_dir}, exc_info=True)`

### FM-11: stockstats raises exception during indicator computation
- **Trigger:** `stockstats.wrap()` or indicator column access raises any exception
- **Response:** Log `ERROR|INDICATOR|Failed to compute indicators for {ticker}: {exc}`. Return `None` — ticker is excluded from screening.
- **Log:** `logger.error("Indicator computation failed", extra={"ticker": ticker}, exc_info=True)`

### FM-12: `--date` is a Saturday or Sunday
- **Trigger:** Resolved trade date has weekday index 5 (Saturday) or 6 (Sunday)
- **Response:** Roll back to the most recent Friday. Print `[Screener] {date} is a weekend — using {friday_date} (most recent trading day).`
- **Not an error** — handled silently with a single info print.

---

## 6. Testing Strategy

**Category:** A (logic changes — mandatory TDD per Rule 09)

### Target test file: `tests/test_screener.py`

New test file (does not conflict with any existing test file).

### Key test scenarios

#### `cache_store.py`
1. `test_cache_miss_when_expired` — Insert manifest entry with `fetched_at` > `PRICE_DATA_VALIDITY_MINS` ago → `cache.get(key)` returns `None`
2. `test_cache_hit_when_fresh` — Insert manifest entry with `fetched_at` 1 minute ago → `cache.get(key)` returns the stored DataFrame
3. `test_cache_put_writes_parquet_and_manifest` — Call `cache.put(key, df)` → verify Parquet file exists and manifest contains the key with a current timestamp
4. `test_cache_handles_missing_manifest` — Delete manifest file → `cache.get()` returns `None` without raising

#### `yf_rate_limiter.py`
5. `test_rate_limiter_blocks_on_minute_limit` — Set `YF_LIMIT_PER_MIN=1`, call `check_and_increment()` twice → second call raises `YFRateLimitExceeded`
6. `test_rate_limiter_resets_after_window` — Insert a manifest entry with `window_start` > 1 minute ago → counter resets, call succeeds
7. `test_rate_limiter_persists_across_runs` — Call `check_and_increment()` N times, create new `YFRateLimiter` instance, call once more → count is N+1 (loaded from disk)

#### `indicator_engine.py`
8. `test_indicators_computed_correctly` — Provide a known OHLCV DataFrame (synthetic, deterministic) → verify RSI, MACD, SMA-50, SMA-200, ATR, vol_ratio are within expected ranges
9. `test_indicators_returns_none_for_sma200_with_short_history` — Provide DataFrame with < 200 rows → `sma_200` field is `None`, other fields populated
10. `test_macdh_crossed_up_3d_true` — Construct DataFrame where `macdh` crosses from negative to positive at row -2 → `macdh_crossed_up_3d` is `True`
11. `test_macdh_crossed_up_3d_false` — Construct DataFrame where `macdh` was negative 5 days ago but no recent crossover → `macdh_crossed_up_3d` is `False`

#### `screening_engine.py`
12. `test_ticker_fails_trend_filter` — Ticker with `close < sma_200` → excluded from results
13. `test_ticker_fails_rsi_range` — Ticker with RSI outside `[35, 65]` using `default` criteria → excluded
14. `test_composite_score_order` — Three tickers with known indicators → verify they are returned sorted descending by score
15. `test_weights_must_sum_to_one` — Load criteria with weights summing to 0.9 → `ValueError` raised at load time

#### `discovery.py`
16. `test_discovery_returns_empty_on_zero_results` — Mock `yfinance.Screener` to return empty → function returns `[]` and logs `WARNING|DISCOVERY|...`
17. `test_discovery_caps_at_100` — Mock screener returning 150 results → function returns exactly 100
18. `test_discovery_saves_result_file` — Mock screener returning 5 results → verify JSON file written to `temp/screener/sector_filters_*.json` with correct fields

#### `data_fetcher.py`
19. `test_fetcher_uses_cache_hit` — Pre-populate cache for a ticker → verify no IB/AV/yfinance calls made for that ticker
20. `test_fetcher_falls_back_to_yfinance_when_ib_unavailable` — Mock `ib.connectAsync` to raise `ConnectionRefusedError` → verify `yf.download` is called
21. `test_fetcher_skips_ticker_with_no_data` — Mock all three sources to return empty → verify ticker excluded from result dict and warning logged

#### `screener.py` (CLI)
22. `test_invalid_sector_selection_exits` — Simulate input `999` at sector prompt → verify `sys.exit(1)` called
23. `test_weekend_date_rollback_saturday` — Pass `--date 2026-03-28` (Saturday) → verify effective date is `2026-03-27`
24. `test_weekend_date_rollback_sunday` — Pass `--date 2026-03-29` (Sunday) → verify effective date is `2026-03-27`
25. `test_ta_exception_does_not_abort_batch` — Mock `ta.propagate()` to raise on first ticker → verify second ticker is still processed and first shows `ANALYSIS FAILED` in output

---

## 7. Implementation Checklist

- [ ] Create `screener/__init__.py`
- [ ] Implement `screener/cache_store.py` (CacheStore class, manifest, Parquet TTL)
- [ ] Implement `screener/yf_rate_limiter.py` (YFRateLimiter, disk persistence, three windows)
- [ ] Implement `screener/indicator_engine.py` (stockstats wrap, manual indicators, macdh crossover)
- [ ] Implement `screener/screening_engine.py` (hard filters, composite score, weight validation)
- [ ] Implement `screener/discovery.py` (yfinance.Screener query, cap, dedup, result file)
- [ ] Implement `screener/data_fetcher.py` (IB async, AV fallback, yfinance fallback, cache integration)
- [ ] Implement `screener/screener.py` (CLI args, UI flow, orchestration, TA integration)
- [ ] Create `config/sectors.json` (8 sectors, metadata only)
- [ ] Create `config/discovery_criteria.json` (3 criteria sets)
- [ ] Create `config/screening_criteria.json` (3 criteria sets)
- [ ] Create `config/watchlists/mining_oil.json`, `technology.json`, `financials.json`, `energy.json`
- [ ] Add `ib_async` to `pyproject.toml` optional dependencies or `requirements-screener.txt`
- [ ] Verify `.env` contains all new variables (already done)
- [ ] Write `tests/test_screener.py` with all 25 scenarios above
- [ ] Run `python -m pytest tests/` — full suite must pass
