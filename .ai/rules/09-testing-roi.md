# TESTING ROI & DECISION MATRIX

## THE "VALUE FOR MONEY" PROTOCOL
Before writing a test, assess the nature of the change. Testing is mandatory for Logic/State (Category A). For config or comment-only changes (Category B), you may skip testing **ONLY with human confirmation**.

## CATEGORY A: MANDATORY TDD (Risk: High)
**Trigger:** Any change that affects *how the system works*.
- **LLM Client Logic:** Changes to `ChatClaudeCode._generate()`, `bind_tools()`, message formatting, response parsing.
- **Data Integrity:** Tool function return values, dataflow vendor selection, config parsing.
- **Control Flow:** Graph routing logic, `conditional_logic.py`, debate round counters.
- **Calculations:** Signal processing (BUY/HOLD/SELL extraction), indicator computation.
- **Stuck States:** Infinite loops, unresponsive agent nodes, subprocess hangs. (CRITICAL)

*Action:* You MUST write a failing test (unit or integration) before fixing.

## CATEGORY B: NO TEST CANDIDATE (Risk: Low)
**Trigger:** Any change that affects *metadata, comments, or non-logic config*.
- **Comments / Docstrings:** Updating docstrings, inline comments, type annotations with no logic change.
- **Config Defaults:** Tweaking default model names or debate round counts in `DEFAULT_CONFIG`.
- **Logging:** Adding/Removing `logger.info` calls.
- **Rules/Docs:** Updating `.ai/rules/`, `AGENTS.md`, `PROJECT_SUMMARY.md`.

*Exclusion:* If a "config" change breaks an agent node or causes the graph to fail, it is **Category A**.

*Action:* Triggers the **Confirmation Protocol**.

## THE CONFIRMATION PROTOCOL (Human-in-the-Loop)
If you determine a task is **Category B**, you MUST NOT write code immediately. You must output:

> **"CLASSIFICATION: Category B (Config/Docs). I propose skipping tests for this change. Proceed? (Yes/No)"**

- **If User says "Yes":** Implement the fix immediately.
- **If User says "No":** Revert to Category A and write a test.
- **Override:** If the user explicitly prompts with "No test needed" or "Hotfix", you may bypass this confirmation.

## UNIT vs INTEGRATION (Cost Optimisation)
- **Prefer Unit Tests (pytest + `unittest.mock`):** For logic, utility functions, and LLM client classes. Mock `subprocess.run` for `ChatClaudeCode` tests.
- **Reserve Integration Tests:** ONLY for critical end-to-end flows like `ta.propagate()` smoke tests. These hit real APIs (LLMs, yfinance) and are slow — run manually, not in CI.

## TESTING TOOL SCRIPTS
When writing tests for scripts that read environment variables:
- Use `monkeypatch.setenv` / `monkeypatch.delenv` for environment isolation in pytest.
- Design functions to accept an `overrides` dict for dependency injection.
- Use `'key' in overrides` (not `overrides.get(key) is not None`) to detect injected values — this lets tests pass explicit `None` to simulate missing credentials.

## REFACTORING & TYPE-CHECKING
- **mypy as Test:** When performing structural refactors (changing Pydantic models, function signatures), the **mypy error** replaces the **Failing Test** for structural changes.
- **Protocol:**
    1. Change the type signature (break mypy).
    2. Fix the code (satisfy mypy).
    3. Run the suite (regression check).

## THE EXIT GATE (REGRESSION)
- **Mandate:** No Category A task is complete until **`python -m pytest tests/`** passes in full.
- **Category B:** Running the full suite is optional but recommended.
