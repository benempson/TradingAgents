---
description: Modifies an existing feature Spec to add requirements or change logic, using a scratchpad plan for execution.
usage: Trigger by typing "/update-spec"
---

# WORKFLOW: UPDATE SPECIFICATION

## 1. SELECT & REVIVE
- **Gate:** Ensure the user has defined the spec to update. If not, ask the user to define it, and exit.
- **Context Lock:** Read the target spec file. Also read `AGENTS.md` and `.ai/rules/` to load architectural context before the interrogation step.

## 2. DEFINE & INTERROGATE (ANTI-ASSUMPTION)
- **User Prompt:** *"What needs to change?"*
- **Gap Analysis (Rule 02):** Analyze the request. Are there ambiguities? Are there missing technical details required for a production-ready implementation?
- **Logic vs Config Scope Check:** Before expanding scope, ask: *"Is this change logic-only (new code path, new tool, behavior change) or config/docs only?"* Confirm explicitly with the user if both appear affected.
- **Unhappy Path Audit:** For every changed or new behavior, ask: *"What should happen when this fails?"* Explicitly probe for LLM errors, subprocess failures, data vendor errors, empty results, and config errors. Do not accept "handle errors gracefully" as an answer — name each case.
- **Constraint:** **STOP and ASK** clarifying questions if anything is unclear. Do not proceed until requirements are sufficient for a complete, production-ready feature.

## 3. ASSIGN CHANGE ID
- **Purpose:** Each spec change receives a unique **change-id** so that multiple changes to the same spec can be developed concurrently without plan file collisions.
- **Format:** A short descriptive kebab-case slug (2-4 words) derived from the change description (e.g., `add-retry-logic`, `fix-tool-parse-fallback`, `add-anthropic-provider`).
- **Constraint:** The slug must be unique among any active `IMPLEMENTATION_PLAN-{spec-stem}-*.md` files in the project root. If a collision is detected, append a numeric suffix.

## 4. UPDATE DOCUMENTATION (SPEC-FIRST)
- **Action:** Append a new section to the bottom of the spec file:
    ```markdown
    ## Revision [Date:YYYY-MM-DD HH:MM] — change-id: {change-id}
    ### Requirements
    - [ ] [The New Requirement — Happy Path]

    ### Unhappy Paths
    - **[Trigger condition]:** [Expected system response — raised exception, log entry, fallback value]
    - *(List every identified failure mode. "N/A" only acceptable if the change has no async ops, subprocess calls, or external data.)*

    ### Technical Plan
    - **Validation:** [Pydantic/boundary checks if any]
    - **Test Strategy:** [Test file to update + key scenarios]
    ```

## 5. TACTICAL PLANNING (THE SCRATCHPAD)
- **Plan File:** Derive the plan filename: `IMPLEMENTATION_PLAN-{spec-stem}-{change-id}.md`.
- **Collision Check:** Check if this plan file already exists.
- **Resume Logic:** If it exists and the header matches, resume from the first unchecked item.
- **Cross-Plan Awareness:** Scan for other active `IMPLEMENTATION_PLAN-{spec-stem}-*.md` files. If any exist, warn about overlapping files.
- **Scope Check (MANDATORY for rename/replace changes):** If the change involves renaming a symbol, config key, or import path, grep `tradingagents/` and `tests/` for the old pattern before writing the plan. Include every matching file in the checklist.
- **Generation (If new):**
    - **Header (CRITICAL):** The first two lines MUST be:
      ```
      > Target Spec: docs/specs/[area]/[filename-spec].md
      > Change ID: {change-id}
      ```
    - **Atomic Decomposition:** Convert high-level spec steps into a detailed checklist.
    - **Mandatory Integration:** Add explicit tasks for **Validation** (Rule 12), **TDD** (Rule 08/09), and **Observability** (Rule 11).
    - **Mandatory Unhappy Path Tasks:** For every failure mode, generate a discrete checklist item covering both the logic (try/except block, fallback) and the log message.

## 5b. COMPLEXITY ASSESSMENT
- **Assessment:** Follow the scoring protocol in `.ai/workflows/_complexity-assessment.md` (Section A). Evaluate the four dimensions against the plan generated in Step 5.
- **Emit** the visible output block (Section B of `_complexity-assessment.md`).
- **Routing:**
    - **Score 0-1** -> **Inline Mode.** Proceed to Step 6 (current sequential execution loop).
    - **Score 2+** -> **Orchestrator Mode.** Proceed to Step 6b (orchestrated execution).
- **Parallel Groups (Orchestrator Mode only):** Append a `## Parallel Groups` section to `IMPLEMENTATION_PLAN-{spec-stem}-{change-id}.md` per Section D of `_complexity-assessment.md`.

## 6. EXECUTION LOOP — INLINE MODE (DRIVEN BY PLAN)
- **Applies when:** Complexity Score 0-1 (Inline Mode).
- **Production-Ready Mandate:** No "TODO" comments or hardcoded placeholders allowed.
- **The Loop:** Read `IMPLEMENTATION_PLAN-{spec-stem}-{change-id}.md`. Find the first unchecked item `[ ]`.
- **Standard Task Protocol:**
    1. **Pre-Code Analysis:** Consult `09-testing-roi.md`. If Category A (Logic), enforce **TDD (Rule 08)**.
    2. **Implementation (Test):** Write failing test cases. Ask user to confirm "Clean Red" failure.
    3. **Implementation (Code):** Write source code to pass tests. Ensure layer separation.
    4. **Observability:** Include "Breadcrumb Logs" (Rule 11) for new execution paths.
    5. **Verification:**
        -   **IF CATEGORY A:** Ask user to run the specific test.
        -   **IF CATEGORY B:** Ask user to verify the change has the expected effect.
- **Update:** Once verified, mark `[x]` in both `IMPLEMENTATION_PLAN-{spec-stem}-{change-id}.md` and the **Target Spec** file.

## 6b. EXECUTION LOOP — ORCHESTRATOR MODE (WAVE-BASED)
- **Applies when:** Complexity Score 2+ (Orchestrator Mode).
- **Protocol:** Follow the Wave Execution Model from `.ai/workflows/_complexity-assessment.md` Section C.2.
- **Research Wave:** Spawn 1-3 Scout agents in parallel to explore each affected layer. Wait for all to complete.
- **Planning Wave (optional):** If 10+ plan items with unclear dependencies, spawn 1 Architect agent to refine parallel groups.
- **Execution Wave(s):**
    1. Read the `## Parallel Groups` section. Identify the first wave of independent groups.
    2. Spawn 1-3 Implementor agents per wave, each with scoped checklist items, file whitelist, and mandatory rule injections (Section C.3).
    3. Wait for wave completion. Mark items `[x]`.
    4. Repeat for subsequent waves.
- **Emit wave status** per Section C.4.
- **After all waves complete:** Proceed to Step 7 (Completion & Security).

## 7. COMPLETION & SECURITY
- **Regression Check:** Ask user to execute `python -m pytest tests/`. Do not proceed until green.

## 8. ADVERSARIAL SECURITY REVIEW (RULE 13)
- **Persona Switch:** Activate Rule 13 ("The Red Team").
- **Action:** Review the code written in this session. **Orchestrator Mode:** Review ALL files modified across ALL Implementor agents (see Section G of `_complexity-assessment.md`). Security review is never delegated to sub-agents.
- **Challenge:** Check for subprocess injection, unvalidated external data, and credential exposure.
- **Output:**
  -   If Secure: "Security Review Passed: [Reason]"
  -   If Vulnerable: "VULNERABILITY FOUND: [Description]. Fixing now..." -> **Loop back to Implementation.**

## 9. GOVERNANCE & ARCHIVE
- **Cleanup:** Delete `IMPLEMENTATION_PLAN-{spec-stem}-{change-id}.md`.
- **Update Operational Reference** (`docs/refs/[area]/[current-filename]-ref.md`, if it exists):
    1. Read the current ref in full before making changes.
    2. Check each section against what changed in this update cycle:
        - **System Constants** — Did any `DEFAULT_CONFIG` values or module constants change?
        - **Data Model** — Did any Pydantic model fields change?
        - **Function Signatures** — Did any public function signatures change?
        - **Edge Cases** — Does the revision's root-cause analysis belong here?
- **PROJECT_SUMMARY.md Decision:** Determine whether this update warrants a `PROJECT_SUMMARY.md` refresh (triggers: new top-level directory in `tradingagents/`, new major feature, modified `AGENTS.md`). If yes, execute the `document-project` workflow.
