# AGENTS.md — TradingAgents Technical Reference

## Project Overview

TradingAgents (v0.2.2) is a multi-agent LLM framework for financial trading analysis built on
**LangGraph** + **LangChain**. A directed acyclic graph of specialised agents (analysts,
researchers, traders, risk managers) collaborates to produce a final BUY / OVERWEIGHT / HOLD /
UNDERWEIGHT / SELL decision for a given ticker and date.

---

## Stack

| Layer | Library | Version floor |
|---|---|---|
| Agent orchestration | `langgraph` | ≥ 0.4.8 |
| LLM abstraction | `langchain-core` | ≥ 0.3.81 |
| OpenAI provider | `langchain-openai` | ≥ 0.3.23 |
| Anthropic provider | `langchain-anthropic` | ≥ 0.3.15 |
| Google provider | `langchain-google-genai` | ≥ 2.1.5 |
| Market data | `yfinance` | ≥ 0.2.63 |
| Technical indicators | `stockstats` | ≥ 0.6.5 |
| CLI | `typer` + `rich` | ≥ 0.21.0 / 14.0.0 |
| Python | | ≥ 3.10 |

Install: `pip install -e .`

---

## LLM Provider System

### How it works

All LLM instantiation flows through a single factory function:

```python
from tradingagents.llm_clients import create_llm_client

client = create_llm_client(provider="openai", model="gpt-5-mini", base_url=None)
llm = client.get_llm()   # returns a LangChain BaseChatModel instance
```

`TradingAgentsGraph.__init__()` calls `create_llm_client` twice — once for
`deep_think_llm` and once for `quick_think_llm` — using the values from `config`.

### Supported providers

| `llm_provider` value | Backing class | Auth env var |
|---|---|---|
| `openai` | `NormalizedChatOpenAI` (Responses API) | `OPENAI_API_KEY` |
| `anthropic` | `NormalizedChatAnthropic` | `ANTHROPIC_API_KEY` |
| `google` | `NormalizedChatGoogleGenerativeAI` | `GOOGLE_API_KEY` |
| `xai` | `NormalizedChatOpenAI` (xAI base URL) | `XAI_API_KEY` |
| `openrouter` | `NormalizedChatOpenAI` (OpenRouter base URL) | `OPENROUTER_API_KEY` |
| `ollama` | `NormalizedChatOpenAI` (localhost:11434) | none |
| `claude_code` | `ChatClaudeCode` (subprocess shim) | **none** |

### Adding a new provider

1. Create `tradingagents/llm_clients/<name>_client.py` with a class extending `BaseLLMClient`.
2. Implement `get_llm() -> BaseChatModel` and `validate_model() -> bool`.
3. Add a branch in `tradingagents/llm_clients/factory.py` → `create_llm_client()`.
4. Add model names to `tradingagents/llm_clients/validators.py` → `VALID_MODELS` (or return
   `True` from `validate_model` to skip validation).

### Normalized wrappers

Each provider wraps its LangChain class in a `Normalized*` subclass that overrides `.invoke()`
to call `normalize_content()`. This strips reasoning/metadata blocks (OpenAI Responses API,
Gemini 3, Claude extended thinking) so downstream agents always receive a plain string.

---

## `claude_code` Provider (shim)

Allows running TradingAgents against a **Claude Max subscription** (no `ANTHROPIC_API_KEY`).
Implemented in `tradingagents/llm_clients/claude_code_client.py`.

### Mechanism

- `ChatClaudeCode` extends LangChain's `BaseChatModel`.
- `_generate()` serialises the LangChain message list to a plain-text conversation and
  pipes it to `claude --print --model <model> --tools "" --no-session-persistence
  --system-prompt <preamble>` via `subprocess.run`.
- **Tool use**: `bind_tools(tools)` converts LangChain tools to OpenAI JSON schemas and stores
  them. The schemas are injected into the conversation's `[System]` block with a strict
  instruction to respond with ONLY a specific JSON object when a tool call is needed:
  ```json
  {"type":"tool_use","id":"call_XXXXXXXX","name":"fn_name","input":{...}}
  ```
  The response is parsed back into `AIMessage(tool_calls=[...])` so LangGraph's `ToolNode`
  can execute the actual Python function.
- **LSP suppression**: The `--system-prompt` flag replaces Claude Code's default system prompt
  (which injects LSP tool descriptions). A short preamble explicitly tells the model it has
  no code/IDE tools and must ignore any it sees.

### Configuration

```python
config["llm_provider"]    = "claude_code"
config["deep_think_llm"]  = "claude-opus-4-5"    # or "claude-opus-4-6"
config["quick_think_llm"] = "claude-sonnet-4-5"  # or "claude-sonnet-4-6"
```

Model names accepted by `claude --model` (short aliases work: `sonnet`, `opus`).
`validate_model()` always returns `True` — the CLI enforces availability.

### Caveats

- Each LLM call spawns a `claude` subprocess. Latency is higher than a direct API call.
- Claude Code must be authenticated (`claude auth` / Claude Max subscription).
- The tool-call JSON format is prompt-engineered; it is reliable but not guaranteed. If
  Claude wraps the JSON in prose, `_parse_tool_call()` falls back to a regex scan for the
  first `{...}` block.

---

## Configuration

### `DEFAULT_CONFIG` keys (`tradingagents/default_config.py`)

| Key | Default | Purpose |
|---|---|---|
| `llm_provider` | `"openai"` | Provider name (see table above) |
| `deep_think_llm` | `"gpt-5.2"` | Model for research managers & portfolio manager |
| `quick_think_llm` | `"gpt-5-mini"` | Model for analysts, researchers, trader |
| `backend_url` | OpenAI v1 URL | Custom API base URL (forwarded to OpenAI-path providers) |
| `google_thinking_level` | `None` | `"high"` / `"minimal"` / `None` |
| `openai_reasoning_effort` | `None` | `"high"` / `"medium"` / `"low"` / `None` |
| `anthropic_effort` | `None` | `"high"` / `"medium"` / `"low"` / `None` |
| `max_debate_rounds` | `1` | Bull vs Bear debate iterations |
| `max_risk_discuss_rounds` | `1` | Risk team debate iterations |
| `max_recur_limit` | `100` | LangGraph recursion guard |
| `results_dir` | `"./results"` | Output directory (env: `TRADINGAGENTS_RESULTS_DIR`) |
| `data_cache_dir` | (auto) | Disk cache for market data |
| `data_vendors` | yfinance for all | Per-category data source overrides |
| `tool_vendors` | `{}` | Per-tool data source overrides (beats category) |

Config is set at graph construction time and propagated to `tradingagents/dataflows/config.py`
via `set_config()`. All dataflow functions call `get_config()` at runtime.

---

## Agent Pipeline (graph execution order)

```
START
  └─ [Market Analyst]  ──tool loop──  [tools_market]
       └─ Msg Clear Market
           └─ [Social Analyst]  ──tool loop──  [tools_social]     (if selected)
               └─ Msg Clear Social
                   └─ [News Analyst]  ──tool loop──  [tools_news]  (if selected)
                       └─ ...
                           └─ [Bull Researcher]  ──debate loop──  [Bear Researcher]
                               └─ [Research Manager]   ← deep_think_llm
                                   └─ [Trader]
                                       └─ [Aggressive Analyst]  ──risk loop──
                                           ├─ [Conservative Analyst]
                                           └─ [Neutral Analyst]
                                               └─ [Portfolio Manager]  ← deep_think_llm
                                                   └─ END
```

- Analysts use `quick_thinking_llm`.
- Research Manager and Portfolio Manager use `deep_thinking_llm`.
- Analyst nodes loop back through their `ToolNode` until `tool_calls` is empty.
- Debate/risk loops are bounded by `max_debate_rounds` / `max_risk_discuss_rounds`.
- After each analyst finishes, a `Msg Clear` node prunes the LangGraph message list to
  prevent unbounded context growth.

### `AgentState` fields (shared across all nodes)

```
company_of_interest, trade_date, sender,
market_report, sentiment_report, news_report, fundamentals_report,
investment_debate_state (InvestDebateState), investment_plan,
trader_investment_plan,
risk_debate_state (RiskDebateState), final_trade_decision,
messages (MessagesState)
```

---

## Data Vendors

Tools are thin wrappers that call `tradingagents/dataflows/interface.py`, which routes to the
configured vendor per category.

| Category config key | Options |
|---|---|
| `core_stock_apis` | `yfinance` (default), `alpha_vantage` |
| `technical_indicators` | `yfinance`, `alpha_vantage` |
| `fundamental_data` | `yfinance`, `alpha_vantage` |
| `news_data` | `yfinance`, `alpha_vantage` |

`ALPHA_VANTAGE_API_KEY` must be set in the environment when using Alpha Vantage.
yfinance requires no key.

---

## Coding Standards

- **Python ≥ 3.10**; type annotations used throughout.
- Pydantic v2 (LangChain's `BaseChatModel` is a Pydantic model) — use `model_name` as a
  field name, not `model`, since `model` is reserved by Pydantic/LangChain.
- LangChain tool definitions use `@tool` decorator or `StructuredTool`; they must be
  serialisable to OpenAI JSON schema via `convert_to_openai_tool`.
- Commit messages follow conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, etc.
- UTF-8 encoding is set process-wide at startup (`sys.stdout.reconfigure(encoding="utf-8")`).
- New providers must NOT require modifying any agent code — only `factory.py` and a new
  `*_client.py` file.

---

## Environment Variables

| Variable | Required by |
|---|---|
| `OPENAI_API_KEY` | `openai` provider |
| `ANTHROPIC_API_KEY` | `anthropic` provider |
| `GOOGLE_API_KEY` | `google` provider |
| `XAI_API_KEY` | `xai` provider |
| `OPENROUTER_API_KEY` | `openrouter` provider |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage data vendors |
| `TRADINGAGENTS_RESULTS_DIR` | Override default results output path |

The `claude_code` provider requires **none** of the above API keys.

---

## Testing

| File | Type | Notes |
|---|---|---|
| `tests/test_claude_code_client.py` | Unit | Mocked subprocess; tests `_generate`, `bind_tools`, message formatting, tool-call parsing |
| `tests/test_ticker_symbol_handling.py` | Unit | Ticker normalisation logic |
| `test_claude_code_shim.py` | Smoke / E2E | Real Claude calls; verifies full AAPL propagation via `claude_code` provider |

Run unit tests: `python -m pytest tests/`
Run smoke test (real calls): `python test_claude_code_shim.py`
