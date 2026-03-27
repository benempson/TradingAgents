---
description: Interactively drafts a structured requirement specification.
---

# Draft New Specification

1.  **Ingest & Interrogate:**
    -   Ask the user: *"What feature or complex fix are we planning?"*
    -   **Gap Analysis:** Analyze the user's response. Is it detailed enough to build?
    -   **Action:** If the request is high-level (e.g., "Add a new analyst"), you MUST ask clarifying questions *before* proposing a plan.
        -   *Example:* "Which data vendors does it use? What tools does it call? What does its report look like?"
    -   **Unhappy Path Probe:** For any feature with async operations, subprocess calls, or external data, walk through this 5-category checklist. For each category, explicitly ask what the fallback behavior or error response should be:
        1. **Network / API errors** — data vendor timeout, yfinance returning empty DataFrame, rate limit exceeded.
        2. **LLM errors** — subprocess non-zero exit, JSON parse failure in tool call response, timeout.
        3. **Empty / zero-result states** — no data returned for a ticker, empty news results, zero indicators.
        4. **Config / init failures** — missing required config key, unsupported provider, invalid model name.
        5. **Graph / async failures** — LangGraph recursion limit hit, infinite tool loop, unresponsive agent node.
    -   **Constraint:** Do not move to Step 2 until every applicable category above has a defined fallback behavior.

2.  **Architectural & Rules Review:**
    -   Read `AGENTS.md` and `PROJECT_SUMMARY.md`.
    -   Analyze the user's intent against the architectural rules (layer separation, provider factory pattern, etc.).

3.  **Drafting (Iterative):**
    -   Propose a **Requirements List** and **Technical Plan** based on `docs/specs/templates/feature-spec.md` (if it exists).
    -   **Constraint (Unhappy Paths — MANDATORY):** For every happy-path requirement, you MUST enumerate its corresponding failure modes in the spec. Each failure mode must specify: the trigger condition, the expected system response, and whether it requires a log entry or raised exception. Do not write "handle errors gracefully" — name the specific case.
    -   **Constraint (Testing):** You MUST identify the target test files and the key test scenarios. Don't just say "we will test it"; say "we need a test that mocks `subprocess.run` to return a non-zero exit code and verifies `RuntimeError` is raised."
    -   **Ask:** *"Here is the structured plan. Are there missing requirements, unhandled failure modes, or architectural risks? (Yes/No/Comment)"*
    -   **Refine:** If the user adds details, update the plan.

4.  **File Generation:**
    -   Once approved, generate the file in `docs/specs/[area]/[feature-name]-spec.md`, where `[area]` mirrors the implementation directory (e.g., `llm_clients`, `agents`, `dataflows`, `graph`).
    -   **Constraint (Failure Modes section — MANDATORY):** The generated spec file MUST contain a `## Failure Modes` section placed before the Implementation Checklist. A spec without this section is incomplete and MUST NOT be saved.
    -   **Action:** Save the file.

5.  **Next Steps:**
    -   Inform the user: *"Spec saved to `docs/specs/[area]/[name]-spec.md`. Run `/implement-spec` when ready to code."*
