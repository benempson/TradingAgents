# ARCHITECTURAL CONSTITUTION

You are working on the `TradingAgents` project.
Your primary source of truth is the file `AGENTS.md` located in the project root.

## CRITICAL INSTRUCTION
Before generating any code or answering any architectural question, you MUST:
1. Read `AGENTS.md`.
2. Read `AGENT.local.md` if it exists (private per-session notes).
3. Verify that your proposed solution follows the provider/factory pattern defined in `tradingagents/llm_clients/`.
4. If you are modifying `trading_graph.py`, `factory.py`, or any `*_client.py`, explicitly state which architectural rule applies to your change.

FAILURE TO COMPLY with `AGENTS.md` will result in rejected code.

---

## MANIFESTO ETHOS & OBJECTIVES

`AGENTS.md` is not a passive technical reference — it is the **AI Architectural Manifesto**: the prime directive that governs every decision made in this codebase. `PROJECT_SUMMARY.md` is its companion: the living record of the current architecture and file tree.

**Both files exist to serve the same objective: ensure that every AI session — regardless of context — produces work of the same architectural quality as if a Principal Engineer were reviewing it.**

The following principles are the foundation of that objective. They are not optional:

### 1. The Source of Truth is Always Read First
No task begins without reading `AGENTS.md` → `AGENT.local.md` → `.ai/rules/` → `PROJECT_SUMMARY.md` in that order. This is non-negotiable. An AI that skips this step is operating blind.

### 2. Every Task Has a Defined Workflow
There are no "freestyle" implementations. All code-writing tasks — bugs, features, refactors — are governed by a named workflow in `.ai/workflows/`. The workflow exists to enforce correctness, testing, security, and documentation in the right order. Bypassing it bypasses all of those safeguards simultaneously.

### 3. Clean Architecture is the Prime Directive
The layer dependency direction (`dataflows ← agents ← graph`) is **inviolable**. A violation doesn't just create a coupling — it destroys the ability to test, swap, or reason about any layer in isolation. This is the architectural decision that all other decisions protect.

### 4. Tests Are Assets, Not Overhead
A test that is deleted to make a build pass is not a solution — it is a regression waiting to happen with no early warning system. Tests, once passing, are permanent. The TDD mandate exists not for ceremony but because bugs caught in red-first tests have a root cause; bugs caught in production do not.

### 5. The Manifesto Must Stay Current
`AGENTS.md` and `PROJECT_SUMMARY.md` are governance documents. When the architecture changes, they must change in the same commit. A stale manifesto is worse than no manifesto — it actively misleads future AI sessions. Section numbers must remain sequential after any edit.

### 6. Specs and References Are Companions
`docs/specs/` (build plans) and `docs/refs/` (operational references) are created in parallel and never replace each other. The spec is the "why and what"; the ref is the "where and how right now". Both are permanent once created.

---

## LAYER DEPENDENCY DIRECTION (INVIOLABLE)

```
dataflows/  ←  agents/  ←  graph/
                              ↑
                         llm_clients/
```

- `dataflows/` has no knowledge of agents or the graph.
- `agents/` may import from `dataflows/` but never from `graph/`.
- `graph/` orchestrates both layers but is not imported by either.
- `llm_clients/` is a standalone layer — it may be imported by `agents/` or `graph/` but never imports from them.

**Forbidden imports (examples):**
- A dataflow function importing anything from `tradingagents/graph/`
- An agent importing from `tradingagents/graph/setup.py`
- A `*_client.py` importing from `tradingagents/agents/`

---

## NEW PROVIDER RULE: THE NORMALIZED WRAPPER

Every new LLM provider MUST follow this two-class pattern:

```python
class NormalizedMyLLM(MyLangChainChatModel):
    """Wraps MyLangChainChatModel to strip reasoning/metadata from responses."""

    def invoke(self, input, config=None, **kwargs):
        result = super().invoke(input, config, **kwargs)
        return normalize_content(result)

class MyLLMClient(BaseLLMClient):
    def get_llm(self) -> NormalizedMyLLM:
        return NormalizedMyLLM(...)

    def validate_model(self) -> bool:
        ...
```

**Why:** LLM providers (especially reasoning models) return metadata blocks (`<thinking>`, `[REASONING]`, etc.) that break downstream agents. `normalize_content()` strips these before the message enters the graph. Every new provider MUST apply this — no exceptions.

**Exception:** `ChatClaudeCode` (the subprocess shim) does NOT use a Normalized wrapper because the shim controls its own output format entirely.

---

## GRAPH STATE: TypedDict, NOT Pydantic

The agent graph state is defined as a TypedDict (`AnnotatedState`) in `tradingagents/graph/trading_graph.py`. Fields are strings, lists, and simple Python types.

- **Do NOT use Pydantic models for graph state.** TypedDict with `Annotated` reducers is the correct pattern.
- **Do NOT add arbitrary keys to state** without updating the `AnnotatedState` definition in the graph.

Key state fields: `company_of_interest`, `trade_date`, `sender`, `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, `investment_debate_state`, `investment_plan`, `trader_investment_plan`, `risk_debate_state`, `final_trade_decision`, `messages`.

---

## TOOL RETURN VALUES: STRINGS ONLY

LangGraph `ToolNode` expects tool functions to return strings (or serializable values that LangChain converts to strings). Tools MUST return `str`, not dicts or Pydantic models.

```python
@tool
def get_stock_data(symbol: str, date: str) -> str:
    """Retrieve stock data."""
    # Good: return a string
    return f"Price on {date}: $200.00"
    # Bad: return {"price": 200.00}  ← breaks ToolNode
```

---

## PYDANTIC v2 FIELD NAMING GOTCHA

LangChain's `BaseChatModel` is a Pydantic v2 model. When defining fields on `ChatClaudeCode` or similar subclasses, use `model_name` (not `model`) — Pydantic v2 reserves the field name `model` internally and will raise a `UserWarning` or validation error.

```python
class ChatClaudeCode(BaseChatModel):
    model_name: str = "claude-sonnet-4-6"  # CORRECT
    # model: str = ...                     # WRONG — reserved by Pydantic v2
```

---

## TWO LLM TIERS: deep_think vs quick_think

The graph uses two LLM tiers configured via `DEFAULT_CONFIG`:
- `deep_think_llm`: Used for Research Manager and Portfolio Manager nodes where quality matters most.
- `quick_think_llm`: Used for analyst nodes, researcher nodes, and the trader — where speed matters more.

New agent nodes must explicitly choose the correct tier. Do not default to `deep_think_llm` for all nodes.

---

## MANIFESTO MAINTENANCE PROTOCOL

When any of the following changes, update `AGENTS.md` and `PROJECT_SUMMARY.md` **in the same commit**:
- A new LLM provider is added
- A new analyst type is added
- A new `DEFAULT_CONFIG` key is introduced
- A new top-level module is created under `tradingagents/`
- The agent pipeline graph topology changes
- A security or coding standard changes

After editing any numbered section in `AGENTS.md` or any rules file, verify that all section numbers remain sequential before committing.
