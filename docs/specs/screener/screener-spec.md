# Technical Screener — Feature Specification
**Status:** IMPLEMENTED
**Squashed:** 2026-03-27
**Created:** 2026-03-27
**Area:** `screener/` (standalone module, sits alongside `tradingagents/`)

---

## 1. Context & Goal

Adds a two-stage pre-filter CLI tool that identifies technically interesting candidates before committing them to `TradingAgentsGraph.propagate()`. Two entry modes: **sector mode** (yfinance Screener API discovery) and **watchlist mode** (hand-curated JSON). Both modes run the same pipeline: OHLCV fetch → indicators → hard filter → composite score → optional deep TA. The screener is a standalone module — it imports from `tradingagents/` read-only and does not modify any existing layer.

---

## 2. Requirements

### 2.1 CLI & UI

| ID | Requirement |
|----|-------------|
| R-UI-01 | Entry: `python screener/screener.py` with `--top-n N`, `--date YYYY-MM-DD`, `--no-ta` |
| R-UI-02 | Startup prompt: `Screen by sector? [y/n]` |
| R-UI-03 | Sector path: numbered list from `config/sectors.json`; comma/space-separated multi-select; invalid → exit(1) |
| R-UI-04 | Sector path: numbered list of discovery criteria from `config/discovery_criteria.json`; invalid → exit(1) |
| R-UI-05 | Watchlist path: numbered list from `config/watchlists/*.json`; invalid → exit(1); skips discovery |
| R-UI-06 | Both paths: numbered list of screening criteria from `config/screening_criteria.json`; invalid → exit(1) |
| R-UI-07 | `--date` defaults to today; Saturday/Sunday rolls back to previous Friday |
| R-UI-08 | Progress printed with module prefixes: `[Discovery]`, `[Fetcher]`, `[Screener]`, `[TA]`; logging module only |
| R-UI-12 | Sector mode: before each sector query print `[Discovery] Fetching top 100 stocks for sector: {sector name}...` |
| R-UI-13 | OHLCV fetch: for each ticker print `[Fetcher] Fetching OHLCV for {ticker}: {N} of {total}` where total is all tickers in the input list and N is 1-based position |
| R-UI-09 | Results table: `Rank \| Ticker \| Score \| RSI \| MACD Hist \| Vol Ratio \| ATR%` |
| R-UI-10 | If `--no-ta` absent and survivors exist: prompt to run `ta.propagate()` sequentially on top-N |
| R-UI-11 | Final summary table after TA: `Ticker \| Score \| RSI \| TA Decision \| Confidence \| Summary` |

### 2.2 Discovery (`discovery.py`)

| ID | Requirement |
|----|-------------|
| R-DISC-01 | `get_sector_shortlist(sector_key, discovery_criteria_id, limiter) -> list[str]` — queries yfinance.Screener with 3M avg volume > 500k + sector match + criteria filters |
| R-DISC-02 | Results capped at 100 tickers per sector (`size=100`) |
| R-DISC-03 | Zero results → log WARNING, return `[]`; orchestrator continues with other sectors |
| R-DISC-04 | Each run saved to `temp/screener/sector_filters_YYYYMMDD-HHMMSS.json` |
| R-DISC-05 | Multi-sector: deduplicated merge; log combined count and duplicates removed |
| R-DISC-06 | `sectors.json` stores metadata only (`id`, `name`, `etf`, `yf_sector`) — no tickers |

### 2.3 Rate Limiter (`yf_rate_limiter.py`)

| ID | Requirement |
|----|-------------|
| R-RATE-01 | All yfinance calls in `discovery.py` and `data_fetcher.py` call `limiter.check_and_increment()` first |
| R-RATE-02 | Three rolling windows: per-minute (env `YF_LIMIT_PER_MIN`, default 100), per-hour (2000), per-day (48000) |
| R-RATE-03 | Window state persisted to `YF_RATE_COUNTER_FILE`; loaded on startup for cross-process accuracy |
| R-RATE-04 | Limit exceeded → raise `YFRateLimitExceeded(window, count, limit)` with reset time |
| R-RATE-05 | Windows reset automatically when `now - window_start >= window_duration` |

### 2.4 OHLCV Fetcher (`data_fetcher.py`)

| ID | Requirement |
|----|-------------|
| R-FETCH-01 | `fetch_ohlcv(tickers, cache, limiter) -> dict[str, pd.DataFrame]` — three-source fallback: IB Gateway → Alpha Vantage → yfinance |
| R-FETCH-02 | Normalised output: `Date` (datetime64), `Open/High/Low/Close/Volume` (float64), ascending, no NaN Close, no partial current-day bars. Cross-source adjustment drift is acceptable at screener resolution. |
| R-FETCH-03 | IB: `ib_async`, 1Y daily `ADJUSTED_LAST`, `asyncio.sleep(10)` between requests (~6 req/min pacing) |
| R-FETCH-04 | IB unavailable (`ConnectionRefusedError`, `asyncio.TimeoutError`) → print fallback message, return `{}` |
| R-FETCH-05 | Alpha Vantage: reuse `get_stock()` from `tradingagents/dataflows/alpha_vantage_stock.py`; switch to yfinance when count >= 20 |
| R-FETCH-06 | yfinance: reuse `yf_retry` from `tradingagents/dataflows/stockstats_utils.py`; call `limiter.check_and_increment()` before each download |
| R-FETCH-07 | Cache-first: check `CacheStore.get(key)` before any source; skip all sources on valid hit |
| R-FETCH-08 | Successful fetches written to cache immediately via `CacheStore.put()` |
| R-FETCH-09 | All sources empty for a ticker → log WARNING, exclude from results dict |

### 2.5 Cache Store (`cache_store.py`)

| ID | Requirement |
|----|-------------|
| R-CACHE-01 | Parquet files stored in `SCREENER_CACHE_DIR` (default `temp/screener/data_cache/`) |
| R-CACHE-02 | `manifest.json` tracks `{ cache_key: { "file": filename, "fetched_at": UTC ISO } }` |
| R-CACHE-03 | `get(key)` returns DataFrame if fresh (`< PRICE_DATA_VALIDITY_MINS`), else `None` |
| R-CACHE-04 | `put(key, df)` writes Parquet then updates manifest atomically (write-temp → rename) |
| R-CACHE-05 | Cache key format: `{TICKER}_ohlcv_1y` |

### 2.6 Indicator Engine (`indicator_engine.py`)

| ID | Requirement |
|----|-------------|
| R-IND-01 | `compute_indicators(df) -> dict \| None` — returns most recent trading day's values |
| R-IND-02 | stockstats indicators: `rsi` (RSI-14), `macd`, `macds`, `macdh`, `close_50_sma`, `close_200_sma`, `atr` (ATR-14) |
| R-IND-03 | Manual indicators: `vol_20_avg`, `vol_ratio = volume / vol_20_avg`, `atr_pct = atr / close * 100` |
| R-IND-04 | `macdh_crossed_up_3d`: True if macdh crossed negative→positive within last 3 rows |
| R-IND-05 | Insufficient data → `None` for that field only; `None` on any hard-filter field = auto-disqualified |
| R-IND-06 | `stockstats.wrap()` exception → log ERROR, return `None` for whole dict |

Return dict fields: `close, sma_50, sma_200, rsi, macd, macds, macdh, macdh_crossed_up_3d, atr, atr_pct, volume, vol_20_avg, vol_ratio`

### 2.7 Screening Engine (`screening_engine.py`)

| ID | Requirement |
|----|-------------|
| R-SCREEN-01 | `apply_criteria(indicators_by_ticker, criteria) -> list[dict]` — hard filter then score, sorted descending |
| R-SCREEN-02 | Hard filters: `close > sma_200`; RSI in `[min, max]`; `macdh > 0 OR macdh_crossed_up_3d`; `vol_ratio >= criteria.value`; `atr_pct` in `[min_atr_pct, max_atr_pct]` |
| R-SCREEN-03 | Composite score: `w1*(1 - abs(rsi-50)/50) + w2*(macdh-hist_min)/(hist_max-hist_min) + w3*min(vol_ratio,3.0)/3.0`; weights from criteria JSON, validated `sum == 1.0` on load |
| R-SCREEN-04 | Result dict: `ticker`, `score`, `indicators`, `filter_results` |

### 2.8 Config Files

| ID | Requirement |
|----|-------------|
| R-CFG-01 | `config/sectors.json` — array of `{ id, name, etf, yf_sector }` |
| R-CFG-02 | `config/discovery_criteria.json` — `{ "criteria": [{ id, name, description, filters }] }` |
| R-CFG-03 | `config/screening_criteria.json` — `{ "criteria": [{ id, name, description, hard_filters, scoring }] }` |
| R-CFG-04 | `config/watchlists/*.json` — `{ id, name, description, tickers }` |
| R-CFG-05 | All configs loaded at startup; JSON parse failure → `ValueError("Config file {path} is invalid JSON: {exc}")` → exit(1) |

---

## 3. Architecture

### File Structure

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
    mining_oil.json  technology.json  financials.json  energy.json
```

### Read-only imports from existing codebase

| Import | Source |
|--------|--------|
| `yf_retry` | `tradingagents/dataflows/stockstats_utils.py` |
| `get_stock()` | `tradingagents/dataflows/alpha_vantage_stock.py` |
| `TradingAgentsGraph` | `tradingagents/graph/trading_graph.py` |
| `DEFAULT_CONFIG` | `tradingagents/default_config.py` |

### New dependency

`ib_async` — added to `pyproject.toml` optional dependencies or `requirements-screener.txt`.

### Environment variables

```
IB_HOST=127.0.0.1  IB_PORT=4002  IB_CLIENT_ID=10
SCREENER_TOP_N=5  SCREENER_CACHE_DIR=temp/screener/data_cache
YF_LIMIT_PER_MIN=100  YF_LIMIT_PER_HOUR=2000  YF_LIMIT_PER_DAY=48000
YF_RATE_COUNTER_FILE=temp/screener/yf_rate_counters.json
```

---

## 4. Data Validation

- **User prompts:** Non-numeric or out-of-range selections exit(1); multi-sector input validated per-value.
- **Config JSON:** Validated at startup (R-CFG-05); missing required fields raise `ValueError`.
- **OHLCV normalisation:** Columns coerced to float64 via `pd.to_numeric(errors='coerce')`; NaN Close rows dropped; partial current-day rows dropped.
- **Indicator fields:** `None` on any hard-filter field disqualifies ticker (guards against recently-listed stocks).
- **Screening weights:** `w1 + w2 + w3 == 1.0` (within float tolerance) validated on config load.
- **Date input:** Validated as `YYYY-MM-DD` via `datetime.strptime` before any network calls.

---

## 5. Failure Modes

| ID | Trigger | Response | Log |
|----|---------|----------|-----|
| FM-01 | IB `ConnectionRefusedError` / `asyncio.TimeoutError` (when `IB_HOST` set) | Raise `IBConnectionFailed`; `screener.py` prompts user: continue with yfinance? If "n" → exit(1). If "y" → retry with `skip_ib=True` | `logger.warning("IB Gateway connection failed", extra={"host":…,"port":…})` |
| FM-02 | IB pacing error for single ticker | Exclude from IB results; falls through to AV/yfinance | `logger.warning("IB pacing error", extra={"ticker":…,"error":…})` |
| FM-03 | `YFRateLimitExceeded` raised mid-batch | Pause; prompt user: `[w]ait Ns / [s]top`. Wait → `time.sleep(N)`, retry full ticker list (cache serves already-fetched). Stop → exit(1). Re-prompts each time limit is hit. | `logger.warning("yfinance rate limit hit", extra={"window":…,"count":…,"limit":…})` |
| FM-04 | AV call count >= 20 in run | Switch remaining tickers to yfinance; continue | `logger.warning("Alpha Vantage near daily limit, switching to yfinance")` |
| FM-05 | yfinance.Screener returns 0 for sector | Return `[]`; if all sectors empty → print message, exit(0) | `logger.warning("No tickers found", extra={"sector":…,"criteria":…})` |
| FM-06 | All tickers fail OHLCV fetch | Print message; exit(1) | `logger.error("All tickers failed OHLCV fetch", extra={"ticker_count":…})` |
| FM-07 | `apply_criteria()` returns empty list | Print message; exit(0) — valid outcome | `logger.info("No tickers passed screening", extra={"criteria":…,"input_count":…})` |
| FM-08 | `ta.propagate()` raises for a ticker | Mark row `TA Decision: ANALYSIS FAILED`; continue batch | `logger.error("propagate() failed", extra={"ticker":…}, exc_info=True)` |
| FM-09 | Config JSON parse failure at startup | Raise `ValueError`; print to stderr; exit(1) | — (raised before logger configured) |
| FM-10 | Cache directory not writable | Print permission message; exit(1) | `logger.error("Cache directory not writable", extra={"path":…}, exc_info=True)` |
| FM-11 | `stockstats.wrap()` exception | Return `None` for whole dict; ticker excluded from screening | `logger.error("Indicator computation failed", extra={"ticker":…}, exc_info=True)` |
| FM-12 | `--date` is Saturday or Sunday | Roll back to most recent Friday; print info message | — (not an error) |

---

## Revision [2026-03-27] — change-id: add-discovery-fetch-progress

### Requirements
- [x] R-UI-12: Before each sector query, print `[Discovery] Fetching top 100 stocks for sector: {sector name}...` to console
- [x] R-UI-13: For each ticker in `fetch_ohlcv()`, print `[Fetcher] Fetching OHLCV for {ticker}: {N} of {total}` to console, where `total` is `len(tickers)` and `N` is 1-based

### Unhappy Paths
- **N/A** — pure observability additions; no new control flow or external calls.

### Technical Plan
- **`screener.py`:** Add `print(f"[Discovery] Fetching top 100 stocks for sector: {sector['name']}...")` inside the sector loop, immediately before the `get_sector_shortlist()` call.
- **`data_fetcher.py`:** Add `print(f"[Fetcher] Fetching OHLCV for {ticker}: {i+1} of {total}", flush=True)` at the start of processing each ticker in `fetch_ohlcv()`. `total = len(tickers)` is known upfront. `flush=True` ensures lines appear immediately for large batches.
- **Test Strategy:** Add to `test_screener_fetcher.py` — assert per-ticker print is called N times for N input tickers. Add to `test_screener_cli.py` — assert sector discovery print fires per sector.

---

## Revision [2026-03-27] — change-id: ib-fallback-prompt

### Requirements
- [x] R-FETCH-10: When `IB_HOST` is **not set**, log `"IB not configured — skipping IB source"` and proceed (current silent behaviour formalised).
- [x] R-FETCH-11: When `IB_HOST` is **set** but IB Gateway connection fails (`ConnectionRefusedError` / `asyncio.TimeoutError`), raise `IBConnectionFailed` rather than silently returning `{}`.
- [x] R-UI-14: `screener.py` catches `IBConnectionFailed` and prompts `"IB Gateway unreachable. Continue with yfinance? [y/n]: "`. If `"n"` → `sys.exit(1)`. If `"y"` → retry `fetch_ohlcv` with `skip_ib=True` (IB bypassed for all remaining calls).
- [x] R-UI-15: The user's answer is remembered for the rest of the run (if rate-limit pause triggers a retry, the IB fallback is not re-prompted).
- [x] R-FETCH-12: `fetch_ohlcv` gains a `skip_ib: bool = False` parameter. When `True`, the IB source block is skipped regardless of env vars.

### Unhappy Paths
- **IB_HOST not set:** Log info only; `skip_ib` remains False; IB source block not entered (existing behaviour, now documented as R-FETCH-10).
- **IB_HOST set, connection times out:** `IBConnectionFailed` raised → propagates to `screener.py` → user is prompted → either exit(1) or retry with `skip_ib=True`.
- **IB_HOST set, user answers "y" twice (if rate-limit forces retry):** `skip_ib=True` is preserved in the retry loop; prompt does not fire again.
- **IB_HOST set, `ib_async` not installed:** Existing `IB is None` branch logs a warning; does NOT raise `IBConnectionFailed` (library absence vs connection failure are distinct failure modes).
- **User presses Ctrl-C at prompt:** `_safe_input` handles `KeyboardInterrupt` → `sys.exit(0)` (consistent with existing prompts).

### Technical Plan
- **`data_fetcher.py`:**
  - Add `class IBConnectionFailed(Exception)` near the top of the file.
  - Modify `_fetch_ib_async`: replace the `except (ConnectionRefusedError, asyncio.TimeoutError)` block that returns `{}` with `raise IBConnectionFailed(host, port, str(exc))`.
  - Add `skip_ib: bool = False` parameter to `fetch_ohlcv`; guard the IB source block with `if resolved_ib_host is not None and not skip_ib:`.
- **`screener.py`:**
  - Import `IBConnectionFailed` from `screener.data_fetcher`.
  - At the OHLCV fetch call site (Step 5), wrap in a try/except that catches `IBConnectionFailed`, prompts user, sets `_skip_ib = True`, and calls `fetch_ohlcv(..., skip_ib=True)`.
  - Track `_skip_ib` as a local variable so the rate-limit retry loop (change-id: rate-limit-pause) can reuse it.
- **Validation:** `IBConnectionFailed` must carry `host` and `port` for the error message.
- **Test Strategy:** `test_screener_fetcher.py` — test that `IBConnectionFailed` is raised when `_fetch_ib_async` receives `ConnectionRefusedError`. `test_screener_cli.py` — mock `fetch_ohlcv` to raise `IBConnectionFailed`; assert user is prompted; assert re-call uses `skip_ib=True`.

---

## Revision [2026-03-27] — change-id: rate-limit-pause

### Requirements
- [x] R-UI-16: When `YFRateLimitExceeded` is raised during `fetch_ohlcv`, instead of crashing, `screener.py` must pause and prompt: `"[w]ait {N}s and continue / [s]top: "`.
- [x] R-UI-17: `N` (wait seconds) is auto-calculated from `exc.reset_at` minus current UTC time, rounded up to the nearest second, minimum 1 s.
- [x] R-UI-18: If user enters `"w"` (wait): `time.sleep(N)`, then re-call `fetch_ohlcv` for the same full ticker list. Already-cached tickers are served from cache (no duplicate fetches). Resume is automatic via cache-hit semantics.
- [x] R-UI-19: If user enters `"s"` (stop): `sys.exit(1)`.
- [x] R-UI-20: The prompt fires every time a limit is hit (user may hit the limit again after waiting if the minute window refills before all tickers are fetched).

### Unhappy Paths
- **Limit hit mid-batch:** `YFRateLimitExceeded` propagates from `limiter.check_and_increment()` inside the yfinance loop in `fetch_ohlcv`. Already-fetched tickers are in cache, so re-calling `fetch_ohlcv` with the full list safely resumes from the correct position via cache hits.
- **User enters invalid input at prompt:** Re-prompt (loop until `"w"` or `"s"` is entered).
- **`exc.reset_at` is in the past:** `wait_secs` resolves to ≤ 0; clamp to 1 s minimum to avoid `time.sleep(0)` or negative values.
- **User presses Ctrl-C during sleep:** `KeyboardInterrupt` propagates naturally; `screener.py` exits immediately (no explicit handling needed — this is correct behaviour).
- **Limit hit again after waiting:** Prompt fires again; user can wait again or stop.

### Technical Plan
- **`screener.py`:** Replace the single `fetch_ohlcv` call and its `try/except YFRateLimitExceeded` block with a `while True` retry loop:
  ```
  _skip_ib = False
  while True:
      try:
          ohlcv_data = fetch_ohlcv(tickers, cache, limiter, trade_date, skip_ib=_skip_ib)
          break
      except IBConnectionFailed as exc:
          [prompt → set _skip_ib=True or exit]
      except YFRateLimitExceeded as exc:
          [calculate wait_secs from exc.reset_at → prompt → sleep or exit]
  ```
- **No changes to `data_fetcher.py` or `yf_rate_limiter.py`** — rate limit propagation is already correct; only the handler in `screener.py` changes.
- **`time` module:** `import time` already present or add it.
- **Validation:** `wait_secs = max(1, math.ceil((exc.reset_at - datetime.now(timezone.utc)).total_seconds()))`.
- **Test Strategy:** `test_screener_cli.py` — mock `fetch_ohlcv` to raise `YFRateLimitExceeded` once then succeed; assert prompt fires; assert `time.sleep` called with correct seconds; assert second call to `fetch_ohlcv` made.

---

## Revision [2026-03-27] — change-id: fix-ta-provider-autodetect

### Requirements
- [x] R-TA-01: Before constructing `TradingAgentsGraph`, resolve the LLM provider via `_resolve_ta_provider()` and print `[TA] Using provider: {provider} (deep: {model}, quick: {model})`.
- [x] R-TA-02: `_resolve_ta_provider()` checks `SCREENER_TA_PROVIDER` env var first (explicit override); accepts any provider name supported by the factory.
- [x] R-TA-03: If `SCREENER_TA_PROVIDER` is not set, auto-detect from API keys in priority order: `OPENAI_API_KEY` → `"openai"`, `ANTHROPIC_API_KEY` → `"anthropic"`, `GOOGLE_API_KEY` → `"google"`.
- [x] R-TA-04: If no API keys are found, default to `"claude_code"` (works with Claude Max subscription; no API key required).
- [x] R-TA-05: When `claude_code` is selected, set `deep_think_llm = "claude-opus-4-6"` and `quick_think_llm = "claude-sonnet-4-6"` in `ta_config`; otherwise keep the `DEFAULT_CONFIG` model names.

### Unhappy Paths
- **`SCREENER_TA_PROVIDER` set to an unsupported value:** `TradingAgentsGraph` factory raises `ValueError` with the unsupported provider name — same error as any other misconfigured provider; no special handling in the screener.
- **No API keys, `claude` CLI not authenticated:** `TradingAgentsGraph` initialises successfully; `ta.propagate()` fails at LLM call time with a `RuntimeError` from the subprocess shim — caught by `_run_ta_for_ticker()` and marked `ANALYSIS FAILED`.
- **N/A:** No async ops, no external data, no subprocess calls within `_resolve_ta_provider` itself.

### Technical Plan
- **`screener/screener.py`:** Add `_resolve_ta_provider() -> str` function (module-level) with constants `_CLAUDE_CODE_DEEP_MODEL` and `_CLAUDE_CODE_QUICK_MODEL` for the default Claude model names. In `main()`, call `_resolve_ta_provider()`, apply result to `ta_config`, update models if `claude_code`, then print the selection before constructing `TradingAgentsGraph`.
- **Environment variable added:** `SCREENER_TA_PROVIDER` — document in `AGENTS.md` env var table.
- **Test Strategy:** `test_screener_cli.py` — 5 parametric-style tests for each resolution path (explicit env var, openai key, anthropic key, google key, no keys → claude_code).
