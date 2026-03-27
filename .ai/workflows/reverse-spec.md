---
description: Analyzes existing code to generate a retroactive Specification file, enabling future Spec-Driven updates.
---

# Reverse Engineer Specification

1.  **Target Identification:**
    -   **Analyze:** Did the user supply the primary entry point of the functionality to be reverse engineered?
        -   **If YES:** Go to step 2.
        -   **If NO:** Ask user: *"Which feature or module area should I document?"*

2.  **Context Load:**
    -   **Action:** Locate the primary entry point and identify its dependency tree (agents, dataflows, llm_clients, config keys).
    -   **Context Load:** Read all relevant source files.

3.  **Code Analysis (The Excavation):**
    -   **Requirements Extraction:** Infer business rules from the logic (e.g., "If the analyst node loops until a non-empty report is returned, then the report is a Required Output").
    -   **Architecture Mapping:** List the actual file structure used (which modules, which providers, which tools).
    -   **Validation Audit:** Check for Pydantic models or manual validation logic to populate the "Data Validation" section.
    -   **Test Coverage:** Check existing test files to populate the "Testing Strategy" section.

4.  **Drafting (The Template Match):**
    -   Read `docs/specs/templates/feature-spec.md` (if it exists).
    -   **Action:** Create a new file mapping the found code to the template sections.
    -   **Constraint:** Be honest. If a test is missing, write "Missing" in the spec. If validation is absent, note that.

5.  **Review & Refinement:**
    -   Present the summary of the generated spec.
    -   Ask user: *"Does this accurately reflect the current functionality? (y/n)"*
    -   *If No:* Allow user to correct assumptions.

6.  **Finalize & Save:**
    -   **Action:** Save the file to `docs/specs/[area]/[feature-name]-spec.md`, where `[area]` mirrors the implementation directory.
    -   **Status:** Set to `**Status:** IMPLEMENTED` since the feature is already built.
    -   **Next Steps:** Inform user: *"Spec saved to `docs/specs/[area]/[name]-spec.md`. To modify this feature, run `/update-spec` and select this file."*
