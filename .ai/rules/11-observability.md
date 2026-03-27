# OBSERVABILITY & DEBUGGING STANDARDS

## THE PHILOSOPHY
Code is not just for execution; it is for diagnosis. You must assume that any complex logic *will* fail eventually, and you (or the user) will need to see *why* without attaching a debugger.

## 1. ENABLING DEBUG MODE
`TradingAgentsGraph` accepts a `debug=True` constructor parameter that enables verbose output during a run (agent node entry/exit, LLM inputs, tool call details). This is a constructor parameter — it is NOT a key in `DEFAULT_CONFIG`.

```python
ta = TradingAgentsGraph(debug=True, config=config)
```

For module-level granular logging, wrap high-frequency or verbose log lines in a level check so they don't fire in production:

```python
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Full conversation payload", extra={"messages": messages})
```

To activate `logging.DEBUG` output during testing or debugging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 2. "BREADCRUMB" LOGGING
You must add logs at critical junctures in the code ("Breadcrumbs"):
1. **Entry Points:** When an agent node starts, an LLM call begins, or a tool is invoked.
2. **Branching:** Inside `if/else` blocks that affect graph routing, data vendor selection, or analyst logic.
3. **Async Results:** When tool results arrive, when subprocess calls return, or when graph state is updated.

## 3. STRUCTURED LOGGING
- **Forbidden:** String concatenation. `logger.info("LLM returned " + str(result))`
- **Required:** `extra` dict parameters. `logger.info("LLM call complete", extra={"provider": provider, "model": model, "tokens": len(response)})`
- **Why:** Structured logging enables filtering by field and machine-readable output — critical when debugging multi-agent runs with interleaved log lines from different analyst nodes.

## 4. THE "BLIND" RULE
If you are unsure why a bug is happening, **DO NOT GUESS**.
- **Action:** Your first move should be to add extensive logging to the suspect module.
- **Ask:** Ask the user to reproduce the issue with `TradingAgentsGraph(debug=True)` or with `logging.basicConfig(level=logging.DEBUG)` and share the output.

## 5. INSTRUMENTATION PERMANENCE (THE "ASSET" RULE)
- **Definition:** Structured logs (`logger.info`, `logger.error`, `logger.warning`) are part of the codebase's feature set, just like the agent logic.
- **Rule:** **NEVER DELETE** valid instrumentation once a bug is fixed.
    - *Reasoning:* If a bug happened once, it will happen again. We need the logs there for the next time.
- **Refinement over Deletion:**
    - If a log is too noisy, do not delete it.
    - **Action:** Downgrade the level (e.g., from `logger.info` to `logger.debug`) or wrap in a level check.
