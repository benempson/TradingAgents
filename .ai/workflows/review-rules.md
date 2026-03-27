---
description: Review and update architectural guardrails
usage: type /review-rules
---

# Architectural Review

1.  **Read Context:** Read `AGENTS.md` and all files in `.ai/rules/`.
2.  **Scan Codebase:** Briefly scan `tradingagents/` (especially `llm_clients/`, `agents/`, `graph/`) for recent patterns that deviate from these rules.
3.  **Report:**
    - Are there any rules being consistently ignored?
    - Are there any new patterns (like a new provider or dataflow vendor) that aren't documented?
    - Is `AGENTS.md` still accurate regarding the tech stack and provider list?
4.  **Propose Updates:** List recommended edits to the rule files to bring them in sync with reality.
