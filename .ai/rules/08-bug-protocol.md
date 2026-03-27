# BUG FIXING PROTOCOL (STRICT ENFORCEMENT)

## THE TRIGGER
Whenever the user asks you to "fix a bug," "solve an issue," or "repair code," you must enter **TDD MODE**.

## THE ALGORITHM
You are STRICTLY FORBIDDEN from generating the fix immediately. You must follow this sequence:

1. **Phase 1: Analysis**
    - Identify the file causing the bug.
    - Identify the existing test file associated with it (or propose creating a new one in `tests/`).

2. **Phase 2: The Reproduction (STOP HERE)**
    - Write a *failing test case* that reproduces the bug.
    - **STOP.** Ask the user to run `python -m pytest tests/<file>.py -v` to confirm it fails.

3. **Phase 3: The Fix**
    - Only AFTER the user confirms the test failed, generate the code fix.

4. **Phase 4: The Verification**
    - Ask the user to run the test again to confirm it passes.

## EXCEPTION
If the user explicitly types "HOTFIX" or "SKIP TEST", you may bypass this protocol. Otherwise, it is mandatory.

## THE "VALID FAILURE" STANDARD (CLEAN RED)
In TDD, a failing test allows you to proceed ONLY if it fails for the right reason.

### CRITERIA
- **Valid Failure (Proceed):** An **AssertionError** where the logic ran but produced the wrong output (e.g., `AssertionError: Expected AIMessage with tool_calls, got empty content`).
- **Invalid Failure (Stop):** A **Setup/Import Error** (e.g., `ModuleNotFoundError`, `AttributeError: Mock has no attribute`, fixture misconfiguration).

### PROTOCOL
- If the test fails due to setup/mocking issues, you **MUST NOT** touch the application code.
- **Action:** Fix the test harness first.
- **Gate:** You may only move to the "Fix" phase when you have a clean `AssertionError` that matches the reported bug behavior.
