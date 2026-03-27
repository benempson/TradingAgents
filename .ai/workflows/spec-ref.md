---
description: Reads an implemented spec and its source code to generate a high-density operational reference document in docs/refs/.
---

# WORKFLOW: GENERATE OPERATIONAL REFERENCE

## 1. SELECT TARGET

- **Check for Pre-specified Target:** If a spec file path was provided in the user's prompt:
    1. Verify the file exists at the specified path. If not, report the error and **STOP**.
    2. Read the file and proceed directly to Source Discovery below.
- **Interactive Discovery (no path provided):** List all `.md` files within `docs/specs/` sub-directories.
- **Gate:** The selected spec MUST have `**Status:** IMPLEMENTED`. If not, **STOP** — only implemented features have operational references.
- **Context Lock:** Read the selected spec in full.
- **Source Discovery:** Identify all source files referenced in the spec (agents, dataflows, llm_clients, config, tests). Read each file to capture the current implementation truth — the spec may have drifted.

## 2. EXTRACT & SYNTHESIZE

From the spec AND the actual source code, extract the following categories. When the spec and source code conflict, **source code wins**.

### a) System Constants
- `DEFAULT_CONFIG` keys (name + purpose + default value + which module reads it)
- Timeout constants and rate limit values (values + code location)
- LLM model name defaults and CLI flag combinations
- Environment variables (name + purpose + which file reads it)

### b) Data Model
- Pydantic model summary: field name + type + constraint. Reference the file path — do NOT inline full model code.
- **Validation Boundary:** Document the exact validation call site — which file and function transforms untrusted external data into a trusted typed value.
- Data flow: describe the path from source (data vendor API) through validation, tool return value, to graph state entry.

### c) Module Architecture
- Module paths + one-line purpose for each key file
- Key class/function signatures (name + parameters + return type)
- Provider/factory wiring: which `create_llm_client` branch creates this class?
- Inter-module dependencies: which agents call which dataflows, which graph nodes call which agents

### d) Configuration Reference
- All config keys consumed by this feature (key name + type + default + effect)
- Which config keys are required vs optional

### e) Test Coverage
- Test file paths + test count per file
- Key test scenarios (what is being verified per test class/function)
- Mock targets (which `subprocess.run`, vendor functions, or `create_llm_client` calls are mocked)

### f) Security Considerations
- Attack vectors + risk level + mitigation (from spec if present, verified against source)

### g) Known Edge Cases & Debugging Notes
- Extracted from spec revision root-cause sections
- Any relevant entries from `MEMORY.md`
- Platform-specific quirks (Windows encoding, subprocess flag requirements, etc.)

## 3. GENERATE REFERENCE DOCUMENT

- **Template:** Use the standardized template at `docs/specs/templates/operational-ref.md` (if it exists).
- **Path:** Save to `docs/refs/[area]/[name]-ref.md`, mirroring the spec's sub-directory structure.
  - Example: `docs/specs/llm_clients/claude-code-client-spec.md` -> `docs/refs/llm_clients/claude-code-client-ref.md`
- **Create directories** if `docs/refs/` or its sub-directories don't exist yet.
- **Constraint:** The reference must be self-contained — a maintainer should be able to understand the feature's operational surface without reading the original spec.

## 4. CROSS-REFERENCE UPDATE

- Add the new ref doc path to `PROJECT_SUMMARY.md` file tree (under a `docs/refs/` section).
- Add to `MEMORY.md` file locations section if the feature has an existing entry there.

## 5. VERIFY

- **Source alignment:** Confirm all function signatures and config keys match the current source files.
- **Env var alignment:** Confirm all environment variable names match those used in the actual code.
- **Spec <-> Ref consistency:** Compare constants and edge cases in the squashed spec against those in the ref. Any item present in one but absent from the other is a gap — resolve before completing.
- **Root-cause transfer:** If the squashed spec has any Change History entries annotated `-> see ref`, confirm each one appears in this ref's Edge Cases section.
- **Output:** "Reference generated: `docs/refs/[area]/[name]-ref.md` — [section count] sections, [line count] lines."
