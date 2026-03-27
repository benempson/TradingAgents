---
description: Trims an implemented spec in-place — purges completed checklists, collapses mechanical revisions, keeps requirement inventory and architectural rationale.
---

# WORKFLOW: SQUASH SPECIFICATION

## 1. SELECT TARGET
- **Check for Pre-specified Target:** If a spec file path was provided in the user's prompt:
    1. Verify the file exists at the specified path. If not, report the error and **STOP**.
    2. Read the file and proceed directly to Step 2.
- **Interactive Discovery (no path provided):** List all `.md` files within `docs/specs/` sub-directories (excluding `docs/specs/templates/`).
- **Gate:** The selected spec MUST have `**Status:** IMPLEMENTED`. If not, **STOP** — only implemented specs are candidates for squashing.
- **Context Lock:** Read the selected file in full.

## 2. CHRONOLOGICAL SYNTHESIS & AUDIT
- **Synthesis:** Process the entire document chronologically — apply each revision and bug fix to the base requirements to construct the feature's *current* state, as if written from scratch today.
- **Classification:** Walk each section of the resulting document and classify it:

### KEEP (always)
- **Context & Goal** — The "why" behind the feature. Permanent architectural rationale.
- **Requirements** — Convert `[x]` checkboxes to a plain bullet inventory (no checkboxes). This becomes the permanent feature manifest.
- **Architecture Plan** — Rewrite as current-state description (not future-tense plan).
- **Security Considerations** — Attack vector + mitigation pairs.
- **Signature behaviours & design details** — Intentional design decisions that define the feature's identity (e.g., the JSON tool-call protocol format, specific CLI flag combinations, timeout values).

### PURGE (always)
- **Implementation Steps checklists** — All items are `[x]`; the code IS the implementation record.
- **"Before/After" code diffs** — Ephemeral; git history preserves these.
- **Phase-gate instructions** — ("STOP. Run tests.", "Ask user to confirm failure.") — build-time ceremony, not operational knowledge.
- **Inline code duplicates** — Python snippets that duplicate what exists in source files verbatim.

### EVALUATE (case-by-case)
- **Revision sections:** Keep root-cause analyses and debugging insights. Purge mechanical checkbox-tracking updates (e.g., revisions that only add `[x]` items without new behavioral context).
- **Inline schema/config snippets:** Keep if they document constraints not obvious from source code. Purge if they duplicate source verbatim.

### ROOT-CAUSE HANDOFF RULE
Root-cause analyses for non-obvious bugs or architectural decisions **MUST NOT be silently purged**. They represent permanent operational knowledge. Choose one:
- **Keep in spec** (only if the rationale is essential to understand a requirement).
- **Transfer to ref** — the preferred destination. Flag the Change History entry with `-> see ref`.

If no ref exists yet, note the items-to-transfer in the Purge Manifest so they are picked up during `spec-ref` generation.

## 3. PURGE MANIFEST
Output a bulleted list of sections/content to be removed, with a one-line justification per item.

## 4. GENERATE SQUASHED SPEC
- Rewrite the spec retaining all KEEP sections and approved EVALUATE(kept) sections.
- **Requirements:** Convert all `- [x]` lines to plain `- ` bullet items (remove checkboxes).
- **Revisions:** Collapse multiple revision sections into a single **Change History** summary — one line per revision: `- [YYYY-MM-DD] One-sentence description`. No sub-sections.
- **Status field:** Update to:
  ```
  **Status:** IMPLEMENTED
  **Squashed:** [YYYY-MM-DD]
  ```
- **Path:** Preserve the original filename and path. Do not rename or move.

## 5. VERIFY
- **Cross-reference check:** Grep for references to this spec's requirement IDs in `PROJECT_SUMMARY.md` and other specs. Confirm they still resolve to content in the squashed version.
- **Test suite alignment:** Grep test files for any requirement ID references (e.g., comments like `# REQ-01`). Verify the IDs still match.
- **Root-cause transfer check:** For every Change History entry annotated `-> see ref`, confirm the content appears in `docs/refs/[area]/[name]-ref.md` Edge Cases. If the ref doesn't exist yet, list the pending transfers.
- **Output:** "Spec squashed: `docs/specs/[area]/[name]-spec.md` — [original line count] lines reduced to [new line count] lines."
