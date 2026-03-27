# 06-error-handling-logging.md
# ERROR HANDLING & LOGGING PROTOCOL

## 1. LOGGING STANDARDS
- **FORBIDDEN:** Do not use `print()` for logging in production code.
- **REQUIRED:** Use Python's standard `logging` module with a named logger:
    ```python
    import logging
    logger = logging.getLogger(__name__)
    # Usage: logger.info(), logger.error(), logger.warning(), logger.debug()
    ```
- **Context:** When logging errors, include the exception and relevant context.
    - *Good:* `logger.error("Failed to call claude CLI", exc_info=True, extra={"model": self.model_name})`
    - *Good:* `logger.info("LLM call complete", extra={"provider": provider, "tokens": len(response)})`

## 2. UNHAPPY PATH PRE-PLANNING MANDATE
Before implementing any feature or change that involves async operations, subprocess calls, external data, or LLM calls, you MUST enumerate its failure modes. This is a design step, not an afterthought.

For each failure mode, define:
1. **Trigger condition** — what causes this failure? (e.g., "claude subprocess exits non-zero", "yfinance returns empty DataFrame", "LangGraph recursion limit hit")
2. **Pipeline response** — what does the agent/graph do? (e.g., raise RuntimeError, return empty report, skip to next node)
3. **Log message** — what is logged for diagnosis?

**Forbidden:** Implementing a feature's happy path and leaving error handling as a TODO. Unhappy paths must be scoped before the first line of code is written.

## 3. STRUCTURED ERROR FEEDBACK
- **Never swallow errors silently** — every failure must produce either a log entry, a raised exception, or a structured return value that callers can act on.
- **Mechanisms:**
    - For LLM calls: raise `RuntimeError` with message including provider, model, and exit code.
    - For tool calls: return empty/null result with a logged warning rather than crashing the agent node.
    - For config errors: raise `ValueError` at graph initialization time, not at first use.
- **Forbidden:** Empty `except` blocks, bare `except: pass`, or returning `None` silently when the caller will not expect it.

## 4. ASYNC SAFETY
- All subprocess calls and external API calls must be wrapped in `try/except` blocks.
- Never swallow an exception silently. Log it, then handle it (or re-raise if it must bubble up).
- Subprocess timeouts (`subprocess.TimeoutExpired`) MUST be caught and turned into a `RuntimeError` with an actionable message.

## 5. THE "NO SILENT CATCH" RULE
- **Forbidden:** Empty or swallowed `except` blocks that discard the error.
    - *Bad:* `except Exception: pass`
    - *Bad:* `except Exception as e: print(e)` (uses print instead of logger)
- **Required:** Every `except` block must:
    1. Log the error using `logger.error()` with context (including `exc_info=True` for unexpected exceptions).
    2. Either re-raise, return a structured error to the caller, or provide fallback behaviour.
- **Reasoning:** Silent exception swallowing is the #1 cause of "nothing happened" bugs where an agent returns empty output with no clue why.

## 6. INSTRUMENTATION PERMANENCE
- **The "Asset" Rule:** Valid instrumentation logs (`logger.info`, `logger.warning`) are considered part of the feature set. Do not delete them once a bug is fixed.
- **Noise Control:** If a log is too verbose, wrap it in a debug-level check rather than deleting it:
    ```python
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Full conversation payload", extra={"messages": messages})
    ```
