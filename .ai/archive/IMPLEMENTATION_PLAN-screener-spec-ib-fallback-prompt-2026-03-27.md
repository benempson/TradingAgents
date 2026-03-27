> Target Spec: docs/specs/screener/screener-spec.md
> Change ID: ib-fallback-prompt
> Routing: Inline (Score 1/4)

## Checklist

### Failing tests (write first — TDD)
- [ ] `test_screener_fetcher.py` — `test_ib_connection_failed_raises`: mock `ib.connectAsync` to raise `ConnectionRefusedError`; assert `_fetch_ib` raises `IBConnectionFailed`.
- [ ] `test_screener_cli.py` — `test_ib_fallback_prompts_user_and_retries`: mock `fetch_ohlcv` to raise `IBConnectionFailed` on first call, return data on second; mock `_safe_input` to return `"y"`; assert second `fetch_ohlcv` call uses `skip_ib=True`.
- [ ] `test_screener_cli.py` — `test_ib_fallback_exits_on_no`: mock `fetch_ohlcv` to raise `IBConnectionFailed`; mock `_safe_input` to return `"n"`; assert `SystemExit(1)`.

### Implementation
- [ ] `screener/data_fetcher.py`: Add `class IBConnectionFailed(Exception)` with `host`, `port`, `reason` attributes.
- [ ] `screener/data_fetcher.py`: In `_fetch_ib_async`, replace the `except (ConnectionRefusedError, asyncio.TimeoutError)` return-`{}` block with `raise IBConnectionFailed(host, port, str(exc))`.
- [ ] `screener/data_fetcher.py`: Add `skip_ib: bool = False` to `fetch_ohlcv` signature; add `and not skip_ib` guard on IB source block.
- [ ] `screener/screener.py`: Import `IBConnectionFailed` from `screener.data_fetcher`.
- [ ] `screener/screener.py`: At Step 5 OHLCV fetch, introduce `_skip_ib = False` local variable and wrap call in a retry loop catching `IBConnectionFailed` → prompt → set `_skip_ib=True` or `sys.exit(1)`. (The retry loop will be expanded by `rate-limit-pause` plan.)

### Verification
- [ ] Run `python -m pytest tests/test_screener_fetcher.py tests/test_screener_cli.py -v` — all new tests green.
- [ ] Run full suite `python -m pytest tests/` — no regressions.

### Spec
- [ ] Mark R-FETCH-10, R-FETCH-11, R-FETCH-12, R-UI-14, R-UI-15 `[x]` in spec.
- [ ] Update FM-01 in spec to reflect new behaviour (raise `IBConnectionFailed` instead of silent return).
