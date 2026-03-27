---
description: Enforces TDD with a Human-in-the-Loop check for skipping tests.
---

# TDD Bug Fix

1.  **Analyze & Classify:**
    -   Analyze the user's request.
    -   **Root Cause Check:** Do you know *exactly* why the bug is happening based on the provided info?
        -   **If NO:** Do not guess. Stop. Ask for logs, tracebacks, or relevant code snippets.
    -   Consult `.ai/rules/09-testing-roi.md`.
    -   Determine if this is **Category A (Logic)** or **Category B (Config/Docs)**.

2.  **Instrumentation (The "Vision" Step):**
    -   **Check:** Is the bug logic obvious?
    -   **If NO:** Do not attempt a fix yet.
        -   **Action:** Add **permanent** logging statements (`logger.info` or `logger.debug`) to the suspect module.
        -   **Note:** These logs will remain in the codebase to assist future debugging. Do not plan to delete them.
        -   **Instruction:** Ask the user to run the scenario with `debug=True` and report the log output.
        -   *Wait for user feedback.*
    -   **If YES:** Proceed to Step 3.

3.  **Scope Assessment & Complexity Routing:**
    -   **Complexity Assessment:** Follow the scoring protocol in `.ai/workflows/_complexity-assessment.md` (Section A). Evaluate the four dimensions (File Radius, Layer Span, Independence, Research Load) and emit the visible output block (Section B).
    -   **Inline Mode (Score 0-1):**
        -   If 1-2 files: Skip the plan — proceed directly to Step 4. No `IMPLEMENTATION_PLAN` file is needed.
        -   If 3+ files but still Score 0-1: Create the plan file (see below) but execute inline (no sub-agents).
    -   **Orchestrator Mode (Score 2+):**
        -   The current session becomes the orchestrator. All implementation will be delegated to sub-agents per the Orchestrator Protocol (Section C of `_complexity-assessment.md`).
    -   **Plan File (for Score 1+ or Orchestrator Mode):**
        -   **Assign Change ID:** Generate a short descriptive kebab-case slug (2-4 words) derived from the bug description (e.g., `fix-tool-call-parse`, `fix-subprocess-timeout`).
        -   **Plan File:** Create `IMPLEMENTATION_PLAN-{change-id}.md` in the project root.
        -   **Header (CRITICAL):** The first two lines MUST be:
            ```
            > Target: {description of the bug — one line}
            > Change ID: {change-id}
            ```
        -   **Checklist:** Break the fix into atomic steps (e.g., "- [ ] Write failing test", "- [ ] Fix JSON parse fallback in `_parse_tool_call`", "- [ ] Run regression suite").
        -   **Parallel Groups (Orchestrator Mode only):** Add a `## Parallel Groups` section per Section D of `_complexity-assessment.md`, mapping checklist items to file ownership groups.
    -   Proceed to Step 4.

4.  **The Fork:**
    -   **IF CATEGORY A:** Proceed to Step 5.
    -   **IF CATEGORY B:**
        -   Ask: *"This appears to be a Config/Docs change (Category B). I recommend skipping the test to save time. Proceed without testing? (Yes/No)"*
        -   **Wait** for user input.
        -   If "Yes": Go to Step 7 (Implement Fix).
        -   If "No": Proceed to Step 5 (Create Reproduction).

5.  **Create Reproduction (TDD):**
    -   **Mode Fork:**
        -   **Inline Mode:** Execute Steps 5-8 as written below (current behavior).
        -   **Orchestrator Mode:** Skip to Step 5b (Orchestrated Execution).
    -   **File Strategy:**
        1.  Identify the target module.
        2.  Locate the existing `tests/test_<module>.py` file.
        3.  Add the reproduction test case to that existing file.
        4.  If (and ONLY if) that causes mocking conflicts (Rule 10), create a **new sibling file**.
    -   **Naming Constraint (CRITICAL):**
        -   New files MUST be named architecturally (e.g., `test_claude_code_client_tool_parsing.py`).
        -   **STRICTLY FORBIDDEN:** `test_temp.py`, `test_repro.py`, `test_fix.py`.
        -   **Extension:** Always `.py`.
    -   **Coding:** Write the failing test case.
    -   **Constraint:** The test MUST fail given the current bug.

5b. **Orchestrated Execution (Orchestrator Mode only):**
    -   Follow the Wave Execution Model from `.ai/workflows/_complexity-assessment.md` Section C.2:
        1.  **Research Wave:** Spawn 1-2 Scout agents to trace the bug across affected layers, identify all files needing changes, and locate existing test fixtures.
        2.  **Update Plan:** Using Scout results, finalize the `## Parallel Groups` section in the plan file.
        3.  **Execution Wave(s):** Spawn Implementor agents per the plan's parallel groups. Each Implementor writes the reproduction test FIRST, then the fix code. Follow the TDD Batching Protocol (Section E).
        4.  **Collect results:** Mark completed items `[x]` in the plan file after each wave.
    -   **After all waves complete:** Proceed to Step 8 (Final Verification) — the orchestrator asks the user to run the full test suite once.
    -   **Skip Steps 6-7** — they are handled within each Implementor agent's execution.

6.  **Failure Analysis (The "False Positive" Check) [Inline Mode only]:**
    -   Ask the user to run the test: `python -m pytest tests/<file>.py::test_<name> -v`
    -   **Analyze Output:**
        -   Is it a **Setup Error** (import errors, fixture misconfiguration, mock attribute errors)? -> **Loop Back:** Fix the test harness.
        -   Is it an **AssertionError** matching the bug? -> **Proceed:** Go to Step 7.
    -   **Constraint:** Do NOT implement the application fix until you have a clean `AssertionError` that matches the reported bug (Rule 08 "Clean Red" standard).

7.  **Implement Fix [Inline Mode only]:**
    -   Write the code to fix the bug.
    -   **If using a plan:** Mark the current checklist item `[x]` after each sub-task is verified.

8.  **Final Verification:**
    -   **Inline Mode:** If a test was written (Category A): Ask user to run the test again to confirm it passes. If no test (Category B): Ask "Please verify the fix has the expected effect."
    -   **Orchestrator Mode:** Ask user to run the full test suite: `python -m pytest tests/ -v`. If any tests fail, identify which Implementor's work caused the failure (match failing test files to the file ownership map) and spawn a targeted fix agent.

9.  **Regression Check:**
    -   **Execute the full test suite** via the terminal (`python -m pytest tests/`) to ensure no regressions.
    -   **Constraint:** Do not mark the task as done until all tests are green.

10.  **Adversarial Security Review (Rule 13):**
    -   **Action:** Briefly scan the fix. Did solving the bug create a security hole? (e.g., removing argument validation to fix a "tool call failed" error).
    -   **Orchestrator Mode:** Review ALL files modified across ALL Implementor agents (see Section G of `_complexity-assessment.md`). Security review is never delegated to sub-agents.
    -   **Output:** Confirm security status.

11.  **Consolidation & Cleanup:**
    -   **Check:** Did you create a separate test file in Step 5?
    -   **Action:** If yes, determine if it can be merged into the main test file.
        -   **If Mergeable:** Move the test case to the main file and delete the separate file.
        -   **If Not Mergeable (Strategy Split):** Ensure the separate file has a permanent, architectural name (Rule 10).
    -   **Final State:** Ensure NO "temporary" files remain, but ALL test logic is preserved.
    -   **Constraint:** DO NOT remove instrumentation logging (Rule 11).
    -   **Plan Cleanup:** If an `IMPLEMENTATION_PLAN-{change-id}.md` was created, delete it now.

12.  **Spec Update:**
    -   **Analyze:** Did this bug fix change a fundamental business rule or data contract?
    -   **Decision:**
        -   **If NO (Implementation Fix):** Stop here unless a spec was mentioned by the user.
        -   **If YES (Requirement Change):** Identify the relevant spec file in `docs/specs/` and append a revision entry.
