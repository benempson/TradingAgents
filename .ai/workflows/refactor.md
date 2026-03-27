---
description: Safely executes structural refactors using type-checker-driven development.
---

# Structural Refactor

1.  **Impact Analysis:**
    -   **Identify Target:** Which function signature, class, or data structure is changing?
    -   **Radius Check:** Briefly search (grep) to see how many files will break.
    -   **Safety Check:** If this is a massive change (>20 files), ask user: *"This will affect [N] files. Proceed?"*
    -   **ADR Gate (Rule 02):** If refactoring a file >300 lines or changing the LLM provider pattern, write an Architecture Decision Record and wait for user approval before generating code.

2.  **Type-First Implementation (The "Red" State):**
    -   **Action:** Modify the source of truth first (e.g., a Pydantic model, a function signature, or a config key).
    -   **Constraint:** Do NOT fix the usage sites yet. Apply only the structural change.
    -   **For Python structural refactors:** Run `mypy tradingagents/` to enumerate all breakages — the mypy errors replace the failing test as the "red" state.
    -   **Acknowledgment:** Explicitly state: *"Types/signatures updated. mypy is now broken. This counts as the 'Failing State'."*

3.  **The Fix Loop (Type-Checker-Driven):**
    -   **Iterate:** Go through the broken files (source AND test files).
    -   **Action:** Update the code to match the new structure.
    -   **Constraint:** Do not change business logic behavior unless forced by the structure. Keep functionality equivalent.
    -   **Mock Ripple Audit (Rule 10):** If you added a new import to a module, grep all test files that mock that module to ensure the new import is also mocked.

4.  **Verification (The "Green" State):**
    -   **Type Check:** Run `mypy tradingagents/` — verify no new `type: ignore` annotations were added to bypass errors.
    -   **Test Run:** Ask user to execute `python -m pytest tests/` — the suite should pass with the new structure.

5.  **Documentation:**
    -   **Spec Drift:** If this changed a data shape or interface defined in a spec, ask to update it.
    -   **AGENTS.md:** If this changed the provider pattern or factory interface, update `AGENTS.md`.
