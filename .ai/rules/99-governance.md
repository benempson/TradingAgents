# 99-governance.md
# META-GOVERNANCE: RULE MAINTENANCE

## THE "LIVING DOCUMENT" PROTOCOL
The files in `.ai/rules/`, `AGENTS.md`, and `PROJECT_SUMMARY.md` are the source of truth for this project. They must not drift from the actual codebase.

## WHEN TO UPDATE RULES
You (the AI) are authorized and expected to propose updates in these scenarios:

1.  **Post-ADR Approval:** Immediately after an "Architecture Decision Record" (ADR) is approved that contradicts existing rules, you MUST proactively offer to update `AGENTS.md` and `.ai/rules/`.
2.  **Conflict Detection:** If a new requirement forces a rule violation, do not bypass it. Ask: *"This requirement conflicts with Rule X. Should we update the rule?"*
3.  **New Pattern Discovery:** If we establish a new standard (e.g., "All forms must now use Zod"), ask to formalize it in the rules.

## DOCUMENTATION SYNC (CRITICAL)
The file `PROJECT_SUMMARY.md` is used to load context for future sessions. It must remain accurate.

1.  **Triggers:**
    -   Creation of a new top-level directory in `tradingagents/`.
    -   Implementation of a new major feature (e.g., a new LLM provider, a new analyst type, a new dataflow vendor).
    -   Modifications to `AGENTS.md`.
2.  **Protocol:**
    -   After completing such a task, you MUST ask: *"Since we have modified the architecture/rules, should I update `PROJECT_SUMMARY.md` to reflect the current state?"*
    -   **Action:** If confirmed, execute the logic from the `document-project` workflow to regenerate the file.

## HOW TO UPDATE RULES
1.  **Draft First:** Show the user the exact text changes.
2.  **User Confirmation:** Must be explicit ("Yes, update the rules").
3.  **Consistency:** Ensure `AGENTS.md` and `.ai/rules/` stay synchronized.

## PROHIBITED BEHAVIOR
-   **Silent Overwrites:** NEVER weaken a safety rule without discussion.
-   **Drift:** Do not generate code that ignores rules just to make a feature work. Fix the code or change the rule.