# DATA VALIDATION STANDARDS

## 1. WHERE PYDANTIC IS AND ISN'T USED IN THIS PROJECT

**Pydantic IS used for:**
- `BaseLLMClient` subclasses (inherit Pydantic via LangChain's `BaseChatModel`)
- Field definitions on `ChatClaudeCode` and similar `BaseChatModel` subclasses
- Any new `BaseLLMClient` or `BaseChatModel` subclass you create

**Pydantic is NOT the pattern for:**
- **Graph state** — uses `TypedDict`/`AnnotatedState` (see Rule 00-architecture)
- **Tool return values** — must be plain strings (see Rule 00-architecture)
- **Config dict** — `DEFAULT_CONFIG` is a plain Python dict

Do not introduce Pydantic models for graph state or tool outputs — it breaks the LangGraph TypedDict contract and `ToolNode` expectations.

## 2. VALIDATION AT SYSTEM BOUNDARIES
Only validate at system boundaries — not inside internal helpers or between agent nodes:
- **External data sources:** yfinance responses, news API payloads, tool return values from the LLM.
- **User-provided config:** `DEFAULT_CONFIG` overrides passed at `TradingAgentsGraph` init time.
- **LLM output:** Tool call arguments from `AIMessage.tool_calls[*]["args"]`.
- **Subprocess output:** Raw stdout from `ChatClaudeCode` and similar clients.

## 3. LOOSE INPUTS, STRICT OUTPUTS
- **Input:** Allow `Optional` fields where data may be absent (partial config overrides, missing fields in an API response).
- **Output:** Ensure all data stored in `AnnotatedState` is clean and typed before it reaches a downstream agent node.

## 4. CONFIG VALIDATION
- All config keys consumed by graph nodes must have defaults in `DEFAULT_CONFIG`.
- If a required config value is missing or of the wrong type, raise `ValueError` at graph initialization time (`TradingAgentsGraph.__init__`), not inside an agent node mid-run.
    - *Good:* Detect missing `llm_provider` in `__init__` and raise immediately.
    - *Bad:* Let a `KeyError` propagate from inside an agent node mid-run.

## 5. LLM OUTPUT PARSING
When parsing structured data (e.g., tool call JSON, BUY/HOLD/SELL signals) from LLM responses:
- Use `json.loads()` inside `try/except json.JSONDecodeError`.
- Fall back to regex extraction if JSON parse fails.
- Log a `logger.warning()` on fallback — this is expected occasionally, not an error.
- Never let a parse failure crash the pipeline; return a structured empty/default value instead.

## 6. TOOL ARGUMENT VALIDATION
When a LangGraph `ToolNode` executes a tool, validate the incoming arguments before acting:
- Check required keys are present in `args` before calling the data vendor.
- Validate date strings are in the expected format (`YYYY-MM-DD`) before passing to yfinance or similar.
- Return a structured error string (not an exception) from tools so the agent can continue gracefully.
