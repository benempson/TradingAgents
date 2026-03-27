---
description: Orchestrator — sequences spec-squash then spec-ref to transition a just-implemented feature into its operational phase.
---

# WORKFLOW: POST-IMPLEMENTATION TRANSITION

## 1. SELECT TARGET

- **Gate:** The user specifies the spec to transition, or this workflow is invoked immediately after `implement-spec` completes.
- **Validation:** Read the spec. Confirm `**Status:** IMPLEMENTED`.
- **Constraint:** If the spec is not IMPLEMENTED, **STOP** — this workflow only applies to completed features.
- **Output:** "Transitioning `docs/specs/[area]/[name]-spec.md` from build phase to operations phase."

## 2. PHASE 1: SQUASH

- Execute the **spec-squash** workflow (`.ai/workflows/spec-squash.md`) against the target spec.
- On completion, the spec is trimmed in-place and marked with `**Squashed:** [date]`.

## 3. PHASE 2: GENERATE REFERENCE

- Execute the **spec-ref** workflow (`.ai/workflows/spec-ref.md`) against the target spec.
- The workflow reads the now-squashed spec + actual source code to produce the operational reference.
- On completion, `docs/refs/[area]/[name]-ref.md` exists with the full operational reference.

## 4. PHASE 3: CROSS-CONSISTENCY CHECK

After both sub-workflows complete, verify alignment between the squashed spec and the generated ref:

- **Constants:** Every `DEFAULT_CONFIG` key or constant mentioned in the spec must appear in the ref's "System Constants" section (and vice versa). Resolve any gaps in either document.
- **Root-cause transfer:** Confirm that every Change History entry annotated `-> see ref` during the squash phase now appears in the ref's Edge Cases section. If any are missing, add them to the ref now.

## 5. PHASE 4: GOVERNANCE

- **PROJECT_SUMMARY.md:** Update the file tree to include the new `docs/refs/[area]/[name]-ref.md` entry. Update the `> Last updated:` header date.
- **MEMORY.md:** Add the ref doc path to MEMORY.md file locations if applicable.
- **Output summary:**
  ```
  Post-implementation complete for [Feature]:
  - Spec squashed: docs/specs/[area]/[name]-spec.md ([original] lines -> [squashed] lines)
  - Reference generated: docs/refs/[area]/[name]-ref.md ([line count] lines)
  - Cross-consistency check: passed
  - PROJECT_SUMMARY.md updated
  ```
