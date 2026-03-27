> Target Spec: docs/specs/screener/screener-spec.md
> Change ID: rate-limit-pause
> Routing: Inline (Score 0/4)
> Note: Depends on ib-fallback-prompt (share the _skip_ib retry loop). Execute after ib-fallback-prompt.

## Checklist

### Failing tests (write first — TDD)
- [ ] `test_screener_cli.py` — `test_rate_limit_pause_waits_and_retries`: mock `fetch_ohlcv` to raise `YFRateLimitExceeded` (window="minute", reset_at=now+65s) on first call, succeed on second; mock `_safe_input` to return `"w"`; mock `time.sleep`; assert `time.sleep` called with ~65; assert second `fetch_ohlcv` call made.
- [ ] `test_screener_cli.py` — `test_rate_limit_pause_stops_on_s`: mock `fetch_ohlcv` to raise `YFRateLimitExceeded`; mock `_safe_input` to return `"s"`; assert `SystemExit(1)`.
- [ ] `test_screener_cli.py` — `test_rate_limit_pause_reprompts_on_invalid_input`: mock `_safe_input` to return `"x"` then `"s"`; mock `fetch_ohlcv` to raise `YFRateLimitExceeded`; assert input called twice, then `SystemExit(1)`.
- [ ] `test_screener_cli.py` — `test_rate_limit_wait_secs_clamped_to_minimum`: `reset_at` is in the past; assert `time.sleep` called with 1 (minimum clamp).

### Implementation
- [ ] `screener/screener.py`: Add `import math` and `import time` (if not already imported); add `timezone` to the `datetime` import.
- [ ] `screener/screener.py`: Replace the Step 5 try/except block with a unified `while True` retry loop that handles both `IBConnectionFailed` and `YFRateLimitExceeded`, with `_skip_ib` tracking across iterations.
- [ ] `screener/screener.py`: Implement `_prompt_rate_limit_wait(exc: YFRateLimitExceeded) -> int` helper that calculates `wait_secs`, prints the prompt, loops until valid input, and returns wait seconds or calls `sys.exit(1)` on `"s"`.

### Verification
- [ ] Run `python -m pytest tests/test_screener_cli.py -v` — all new tests green.
- [ ] Run full suite `python -m pytest tests/` — no regressions.

### Spec
- [ ] Mark R-UI-16 through R-UI-20 `[x]` in spec.
- [ ] Update FM-03 in spec to reflect new interactive pause behaviour (was: exit(1)).
