---
description: Implements new functionality with strict architectural alignment, mandatory testing, and explicit user approval.
---

# New Feature Implementation

1.  **Analysis & Strategy Formulation:**
    -   **Analyze Request:** Re-state the requirement to ensure understanding.
    -   **Gap Analysis (Rule 02):** Are there any ambiguities regarding which layer is affected, edge cases, or error handling?
        -   **Action:** If yes, ask clarifying questions now. Do not propose a plan yet.
    -   **Rule Check:** Consult `AGENTS.md`. Identify which modules need modification (dataflows, agents, llm_clients, graph).
    -   **Layer Impact Check (Rule 02):** Does this change cross architectural layers? Confirm dependency direction is clean (dataflows ← agents ← graph).
    -   **ROI Check:** Consult `.ai/rules/09-testing-roi.md`.
        -   Determine: **Category A (Logic/Flow)** or **Category B (Config/Docs)**.
    -   **Test Strategy:** If Category A, define *where* the test will live (`tests/test_<module>.py`) and *what* the key assertions will be.

2.  **The Proposal (STOP & CONFIRM):**
    -   **Action:** Present a concise plan to the user containing:
        1.  **Requirement:** "I understand you want to..."
        2.  **Classification:** "Category [A/B] (Testing [Required/Optional])"
        3.  **Architecture:** "I will modify `[File A]`, create `[File B]`..."
        4.  **Test Plan:** "I will test `[Scenario]` in `tests/[test_file].py`."
    -   **Constraint:** Ask: *"Does this plan align with your intent? (Yes/No)"*
    -   **Wait:** **STOP** and wait for user confirmation.

3.  **Implementation (Code & Test):**
    -   **Action:** Write the source code following the module layer conventions in `AGENTS.md`.
    -   **Constraint (Validation):** If this involves external data or user config, you MUST validate at the system boundary (Rule 12).
    -   **Constraint (Observability):** You MUST include "Breadcrumb Logs" (Rule 11) for all key actions (LLM calls, tool invocations, graph routing decisions).
    -   **Constraint:** Ensure strict separation of concerns — dataflow logic stays in `dataflows/`, agent prompts stay in `agents/`, LLM wiring stays in `llm_clients/`.
    -   **Action:** Write/Update the corresponding test (if Category A).

4.  **Verification:**
    -   **IF CATEGORY A:** Instruct user: "Run `python -m pytest tests/[test_file].py -v`. Does it PASS?"
    -   **IF CATEGORY B:** Confirm the config change has the expected effect.

5.  **Adversarial Security Review (Rule 13):**
    -   **Persona Switch:** Activate Rule 13 ("The Red Team").
    -   **Action:** Review the code you just wrote.
    -   **Challenge:** Attempt to construct a theoretical exploit.
        -   *Check:* Did we use `shell=True` or string-interpolated subprocess calls?
        -   *Check:* Are external data values logged or passed through without validation?
        -   *Check:* Are any credentials or API keys at risk of exposure?
    -   **Output:**
        -   If Secure: "Security Review Passed: [Reason]"
        -   If Vulnerable: "VULNERABILITY FOUND: [Description]. Fixing now..." -> **Loop back to Implementation.**

6.  **Regression Check:**
    -   **Execute the full test suite** via the terminal (`python -m pytest tests/`) to ensure no regressions.
    -   **Constraint:** Do not mark the task as done until all tests are green.

7.  **Governance & Cleanup:**
    -   **Documentation:** Read `.ai/rules/99-governance.md`.
        -   Ask: *"Since we added a new feature, should I update `PROJECT_SUMMARY.md` to keep the context fresh?"*
