---
description: Standard context loading sequence for workflows that need architectural context. Referenced by implement-spec, update-spec, and new-func workflows.
type: include
---

# CONTEXT LOAD PROTOCOL

This file is an **include** — it is referenced by other workflows, not invoked directly.

---

## Protocol

Before any planning or implementation, load architectural context in this order:

1. **`AGENTS.md`** — The Root Manifesto and Prime Directive.
2. **`AGENT.local.md`** — Private per-session notes (if it exists — not committed to git).
3. **`.ai/rules/`** — The constitutional framework (always-active behavioural rules).
4. **`PROJECT_SUMMARY.md`** — The current state of the architecture and file tree.

**Constraint:** Do not skip this sequence. An AI that operates without reading these files is operating blind and may violate layer separation, testing mandates, or security rules.
