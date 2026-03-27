---
description: Aggregates all rules, workflows, and manifestos into a single "Bootstrap" document for new AI sessions.
---

# Generate Governance System Export

1.  **Collection Strategy:**
    -   Identify the Root Manifesto: `AGENTS.md`.
    -   Identify the Context Summary: `PROJECT_SUMMARY.md`.
    -   List all Rule files: `.ai/rules/*.md`.
    -   List all Workflow files: `.ai/workflows/*.md`.

2.  **Aggregation:**
    -   Read the content of all identified files.
    -   Create a combined Markdown document named `GOVERNANCE_SYSTEM.md`.

3.  **Formatting Structure:**
    The output file MUST follow this structure:

    ```markdown
    # TRADINGAGENTS - GOVERNANCE SYSTEM EXPORT
    > Generated on: [Current Date]
    > Purpose: Paste this into a new AI session to load full architectural context.

    ---
    ## PART 1: ROOT MANIFESTO (AGENTS.md)
    [Content of AGENTS.md]

    ---
    ## PART 2: PROJECT CONTEXT (PROJECT_SUMMARY.md)
    [Content of PROJECT_SUMMARY.md]

    ---
    ## PART 3: ARCHITECTURAL RULES
    ### [Filename 1]
    [Content of Rule 1]
    ...

    ---
    ## PART 4: OPERATIONAL WORKFLOWS
    ### [Filename 1]
    [Content of Workflow 1]
    ...
    ```

4.  **Execution:**
    -   Save `GOVERNANCE_SYSTEM.md` to the project root.
    -   **Action:** Provide a final message: "Governance System exported to `GOVERNANCE_SYSTEM.md`. You may now copy/paste this file's content into any new chat."
