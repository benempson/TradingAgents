---
description: Shared adversarial security review protocol (Rule 13). Referenced by implement-spec, update-spec, fix-bug, and new-func workflows.
type: include
---

# ADVERSARIAL SECURITY REVIEW (RULE 13)

This file is an **include** — it is referenced by other workflows, not invoked directly.

---

## Protocol

1. **Persona Switch:** Activate Rule 13 ("The Red Team").
2. **Scope:**
   - **Inline Mode:** Review the code written in this session.
   - **Orchestrator Mode:** Review ALL files modified across ALL Implementor agents. Security review is never delegated to sub-agents — they see only their slice; the review needs the full picture.
3. **Challenge:** Attempt to construct a theoretical exploit against the changes made:
   - *Check:* Did we use `shell=True` or string-interpolated subprocess commands?
   - *Check:* Are external data values (LLM output, tool arguments, API responses) validated at the boundary before use?
   - *Check:* Could any new config key expose credentials or enable injection?
   - *Check:* Are API keys or secrets at risk of appearing in logs, error messages, or stack traces?
   - *Check:* Are tool call arguments from the LLM validated before being passed to file system operations, network calls, or shell commands?
4. **Output:**
   - If Secure: `"Security Review Passed: [Reason]"`
   - If Vulnerable: `"VULNERABILITY FOUND: [Description]. Fixing now..."` → **Loop back to Implementation.**
