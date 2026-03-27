---
description: Shared 5-category failure mode probe for spec drafting and updates. Referenced by draft-spec and update-spec workflows.
type: include
---

# UNHAPPY PATH PROBE (5-CATEGORY CHECKLIST)

This file is an **include** — it is referenced by other workflows, not invoked directly.

---

## Protocol

For any feature or change involving async operations, subprocess calls, or external data, walk through this 5-category checklist. For each category, explicitly ask what the fallback behavior or error response should be:

1. **Network / API errors** — data vendor timeout, yfinance returning empty DataFrame, rate limit exceeded.
2. **LLM errors** — subprocess non-zero exit, JSON parse failure in tool call response, timeout.
3. **Empty / zero-result states** — no data returned for a ticker, empty news results, zero indicators.
4. **Config / init failures** — missing required config key, unsupported provider, invalid model name.
5. **Graph / async failures** — LangGraph recursion limit hit, infinite tool loop, unresponsive agent node.

**Constraint:** Do not proceed until every applicable category above has a defined fallback behavior. Do not accept "handle errors gracefully" as an answer — name the specific case, the trigger condition, the expected system response, and whether it requires a log entry or raised exception.
