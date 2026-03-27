---
description: Executes a TDD-based implementation of an approved specification with persistent state.
usage: Trigger by typing "/implement-spec"
---

# WORKFLOW: EXECUTE SPECIFICATION (TDD MODE)

## 1. SELECT & LOCK
- **Gate:** Has the user specified the spec to work on? If not, ask them to specify it and exit.
- **Context Lock:** Explicitly output: `Target Spec: docs/specs/[area]/[filename-spec.md]`.
- **Plan File:** Derive the plan filename: `IMPLEMENTATION_PLAN-{spec-stem}.md` where `{spec-stem}` is the spec's filename without the `-spec.md` suffix (e.g. `claude-code-client` from `docs/specs/llm_clients/claude-code-client-spec.md`).
- **Validation:** Verify status is `APPROVED`. Review implementation steps.
- **Context Load:** Read `AGENTS.md` and `.ai/rules/` to ensure architectural context is active.
- **Constraint:** If the spec is ambiguous or lacks detail for a production-ready implementation, **STOP** and ask for clarification.

## 2. TACTICAL PLANNING (THE SCRATCHPAD)
- **Collision Check:** Check if `IMPLEMENTATION_PLAN-{spec-stem}.md` exists in the root.
- **Resume Logic:**
    - If it exists and the first line matches `> Target Spec: docs/specs/[area]/[current_filename-spec].md`: Proceed to step 3.
- **Generation (If new):**
    - **Header (CRITICAL):** The first line MUST be: `> Target Spec: docs/specs/[area]/[filename-spec].md`.
    - **Unhappy-Path Gate (MUST RUN FIRST):** Before listing any implementation tasks, read the spec's `### Failure Modes` (or `### Unhappy Paths`) section. Transcribe each failure mode as an explicit checklist item covering: (a) the service/function that can fail, (b) the fallback behavior or raised exception, and (c) any required log message. If the spec has no failure modes section, **STOP** and ask the user to define them before continuing.
    - **Atomic Decomposition:** Convert all remaining high-level spec steps into a detailed checklist (e.g., "- [ ] Write failing test for subprocess non-zero exit", "- [ ] Implement `_parse_tool_call` fallback regex").
    - **Mandatory Integration:** Add explicit tasks for **Validation** (Rule 12), **TDD** (Rule 08/09), and **Observability** (Rule 11).
    - **Constraint (Production-Ready):** No "TODO" comments or hardcoded placeholders for dynamic content allowed.

## 2b. COMPLEXITY ASSESSMENT
- **Assessment:** Follow the scoring protocol in `.ai/workflows/_complexity-assessment.md` (Section A). Evaluate the four dimensions (File Radius, Layer Span, Independence, Research Load) against the plan generated in Step 2.
- **Emit** the visible output block (Section B of `_complexity-assessment.md`).
- **Routing:**
    - **Score 0-1** -> **Inline Mode.** Proceed to Step 3 (current sequential execution loop).
    - **Score 2+** -> **Orchestrator Mode.** Proceed to Step 3b (orchestrated execution).
- **Parallel Groups (Orchestrator Mode only):** Append a `## Parallel Groups` section to `IMPLEMENTATION_PLAN-{spec-stem}.md` per Section D of `_complexity-assessment.md`, mapping checklist items to file ownership groups with dependency annotations.

## 3. EXECUTION LOOP — INLINE MODE (DRIVEN BY PLAN)
- **Applies when:** Complexity Score 0-1 (Inline Mode).
- **Production-Ready Mandate:** It is strictly forbidden to use hardcoded placeholders for dynamic data or leave `TODO` comments.
- **The Loop:** Read `IMPLEMENTATION_PLAN-{spec-stem}.md`. Find the first unchecked item `[ ]`.
- **Standard Task Protocol:**
    1. **Pre-Code Analysis:** Consult `09-testing-roi.md`. If Category A (Logic), enforce **TDD (Rule 08)**. If external data or config input, verify **Validation (Rule 12)**.
    2. **Implementation (Test):** Write the failing test case in `tests/test_<module>.py`. Ask user to run it to confirm "Clean Red" failure.
    3. **Implementation (Code):** Write source code to pass the test. Ensure layer separation (dataflows <- agents <- graph).
    4. **Observability:** Include "Breadcrumb Logs" (Rule 11) for all key execution paths.
    5. **Verification:**
        -   **IF CATEGORY A:** Ask user to run `python -m pytest tests/[test_file].py -v`.
        -   **IF CATEGORY B:** Ask user to verify the config/docs change has the expected effect.
    -   **Coverage:** New business logic MUST have unit tests. Every code path that can fail must have a test.
- **Update:** Once verified, mark `[x]` in `IMPLEMENTATION_PLAN-{spec-stem}.md` and the **Target Spec** file.

## 3b. EXECUTION LOOP — ORCHESTRATOR MODE (WAVE-BASED)
- **Applies when:** Complexity Score 2+ (Orchestrator Mode).
- **Protocol:** Follow the Wave Execution Model from `.ai/workflows/_complexity-assessment.md` Section C.2.
- **Research Wave:**
    1. Spawn 1-3 Scout agents (subagent_type: `Explore`) in parallel, each exploring a different affected layer or area.
    2. Wait for all Scouts to complete. Aggregate findings.
    3. If the plan needs refinement based on Scout results, update the checklist and `## Parallel Groups` section.
- **Planning Wave (optional):**
    - If the plan has 10+ items and the dependency structure is unclear, spawn 1 Architect agent (subagent_type: `Plan`) to refine the parallel groups and identify the optimal wave ordering.
    - Transcribe the Architect's output into the plan file.
- **Execution Wave(s):**
    1. Read the `## Parallel Groups` section. Identify the first wave of independent groups.
    2. Spawn 1-3 Implementor agents (subagent_type: `general-purpose`) per wave. Each receives its checklist items, file whitelist, and the mandatory rule injections (Section C.3 of `_complexity-assessment.md`).
    3. Wait for all Implementors in the wave to complete.
    4. Mark completed items `[x]` in the plan file and the Target Spec.
    5. Repeat for subsequent waves until all items are checked.
- **Emit wave status** before and after each wave (Section C.4 of `_complexity-assessment.md`).
- **After all waves complete:** Proceed to Step 4 (Completion & Security).

## 4. COMPLETION & SECURITY
- **Regression Check:** Ask user to execute the full test suite (`python -m pytest tests/`). Do not proceed until the suite is green.

## 5. ADVERSARIAL SECURITY REVIEW (RULE 13)
- **Persona Switch:** Activate Rule 13 ("The Red Team").
- **Action:** Review the code written in this session. **Orchestrator Mode:** Review ALL files modified across ALL Implementor agents (see Section G of `_complexity-assessment.md`). Security review is never delegated to sub-agents.
- **Challenge:** Attempt to construct a theoretical exploit.
  -   *Check:* Did we use `shell=True` or string-interpolated subprocess commands?
  -   *Check:* Are external data values validated at the boundary?
  -   *Check:* Could any new config key expose credentials or enable injection?
- **Output:**
  -   If Secure: "Security Review Passed: [Reason]"
  -   If Vulnerable: "VULNERABILITY FOUND: [Description]. Fixing now..." -> **Loop back to Implementation.**

## 6. GOVERNANCE & ARCHIVE
- **Cleanup:** Delete `IMPLEMENTATION_PLAN-{spec-stem}.md`.
- **Post-impl:** Run `/spec-post-impl` to transition the spec to its post-implementation format.
