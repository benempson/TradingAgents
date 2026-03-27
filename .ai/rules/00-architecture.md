# ARCHITECTURAL CONSTITUTION

You are working on the `TradingAgents` project.
Your primary source of truth is the file `AGENTS.md` located in the project root.

## CRITICAL INSTRUCTION
Before generating any code or answering any architectural question, you MUST:
1. Read `AGENTS.md`.
2. Verify that your proposed solution follows the provider/factory pattern defined in `tradingagents/llm_clients/`.
3. If you are modifying `trading_graph.py`, `factory.py`, or any `*_client.py`, explicitly state which architectural rule applies to your change.

FAILURE TO COMPLY with `AGENTS.md` will result in rejected code.

---

## LAYER DEPENDENCY DIRECTION (INVIOLABLE)

```
dataflows/  ←  agents/  ←  graph/
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

**Exception:** `ChatClaudeCode` (the subprocess shim) does NOT use a Normalized wrapper because `normalize_content()` is applied in a different way and the shim controls its own output format.

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
- `deep_think_llm`: Used for analyst nodes and debate nodes where quality matters most.
- `quick_think_llm`: Used for routing/classification nodes where speed matters.

New agent nodes must explicitly choose the correct tier. Do not default to `deep_think_llm` for all nodes — check `AGENTS.md` for the intended tier per node type.
