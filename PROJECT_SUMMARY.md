# PROJECT_SUMMARY.md — TradingAgents File & Folder Reference

## Top-level Layout

```
TradingAgents/
├── tradingagents/          # Core Python package
│   ├── agents/             # All agent node implementations
│   ├── dataflows/          # Market data fetching & caching
│   ├── graph/              # LangGraph wiring, orchestration, I/O
│   └── llm_clients/        # LLM provider abstraction layer
├── cli/                    # Interactive CLI (Typer)
├── tests/                  # Automated tests
├── build/                  # Setuptools build artefacts (not source of truth)
├── main.py                 # Quick example / scratch script
├── test.py                 # Legacy scratch test
├── test_claude_code_shim.py  # E2E smoke test for the claude_code provider
├── pyproject.toml          # Package metadata & dependencies
├── AGENTS.md               # Technical reference (coding standards, providers, config)
└── PROJECT_SUMMARY.md      # This file
```

---

## `tradingagents/` — Core Package

### `tradingagents/default_config.py`
Single source of truth for all configurable parameters: LLM provider, model names, data
vendors, debate rounds, recursion limits, and file paths. Always copy before mutating:
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "claude_code"
```

### `tradingagents/llm_clients/`

The provider abstraction layer. All LLM construction goes through here.

| File | Purpose |
|---|---|
| `factory.py` | `create_llm_client(provider, model, base_url, **kwargs)` — the single entry point. Branches by provider string. |
| `base_client.py` | `BaseLLMClient` ABC (`get_llm`, `validate_model`) + `normalize_content()` helper that strips reasoning/metadata blocks from responses. |
| `openai_client.py` | `NormalizedChatOpenAI` + `OpenAIClient` — handles openai, ollama, openrouter, xai. Uses Responses API for native OpenAI. |
| `anthropic_client.py` | `NormalizedChatAnthropic` + `AnthropicClient` — handles anthropic. |
| `google_client.py` | `NormalizedChatGoogleGenerativeAI` + `GoogleClient` — handles google. |
| `claude_code_client.py` | `ChatClaudeCode` + `ClaudeCodeClient` — **custom shim** that routes calls through the `claude --print` CLI (no API key needed, uses Claude Max subscription). |
| `validators.py` | `VALID_MODELS` dict + `validate_model(provider, model)` — ollama/openrouter/claude_code accept any model name. |
| `__init__.py` | Re-exports `create_llm_client`. |

### `tradingagents/graph/`

LangGraph wiring. The main entry point for consumers of the framework.

| File | Purpose |
|---|---|
| `trading_graph.py` | **`TradingAgentsGraph`** — the top-level class. `__init__` builds the LLM clients and graph; `propagate(ticker, date)` runs the analysis and returns `(final_state, decision)`. |
| `setup.py` | **`GraphSetup`** — constructs the `StateGraph`, adds all nodes and edges, and compiles it. Graph topology lives here. |
| `propagation.py` | **`Propagator`** — creates the initial `AgentState` for a ticker/date. |
| `conditional_logic.py` | **`ConditionalLogic`** — routing functions (`should_continue_market`, `should_continue_debate`, `should_continue_risk_analysis`, etc.) that decide which node runs next. |
| `signal_processing.py` | **`SignalProcessor`** — extracts the final BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL label from the raw Portfolio Manager output text. |
| `reflection.py` | **`Reflector`** — post-trade memory update logic (called via `ta.reflect_and_remember(returns)`). |
| `__init__.py` | Re-exports `TradingAgentsGraph`. |

### `tradingagents/agents/`

One file per agent role. Each file exposes a `create_<name>(llm, ...)` factory that returns a
LangGraph node function (`state -> dict`).

#### `agents/analysts/` — Data-gathering agents (use `quick_think_llm`)

| File | Agent | Tools used |
|---|---|---|
| `market_analyst.py` | Market Analyst | `get_stock_data`, `get_indicators` |
| `social_media_analyst.py` | Social Media Analyst | (sentiment tools) |
| `news_analyst.py` | News Analyst | `get_news`, `get_global_news` |
| `fundamentals_analyst.py` | Fundamentals Analyst | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` |

Pattern used by all analysts:
```python
chain = prompt | llm.bind_tools(tools)
result = chain.invoke(state["messages"])
# If tool_calls present → ToolNode handles them and re-invokes analyst
# If no tool_calls → result.content is the final report
```

#### `agents/researchers/` — Investment thesis (use `quick_think_llm`)

| File | Agent |
|---|---|
| `bull_researcher.py` | Bull Researcher — argues for investment |
| `bear_researcher.py` | Bear Researcher — argues against investment |

These run in a debate loop (`max_debate_rounds`) alternating between themselves until the
Research Manager signals a decision.

#### `agents/managers/` — Decision makers (use `deep_think_llm`)

| File | Agent |
|---|---|
| `research_manager.py` | Research Manager — judges bull/bear debate, produces `investment_plan` |
| `portfolio_manager.py` | Portfolio Manager — judges risk debate, produces `final_trade_decision` |

#### `agents/risk_mgmt/` — Risk debate (use `quick_think_llm`)

| File | Agent |
|---|---|
| `aggressive_debator.py` | Aggressive Analyst — argues for higher risk |
| `conservative_debator.py` | Conservative Analyst — argues for lower risk |
| `neutral_debator.py` | Neutral Analyst — mediates |

Run in a round-robin loop (`max_risk_discuss_rounds`) before the Portfolio Manager decides.

#### `agents/trader/`

| File | Agent |
|---|---|
| `trader.py` | Trader — translates the investment plan into a specific trading proposal |

#### `agents/utils/`

| File | Purpose |
|---|---|
| `agent_states.py` | `AgentState`, `InvestDebateState`, `RiskDebateState` TypedDicts |
| `agent_utils.py` | Abstract tool functions (`get_stock_data`, `get_indicators`, etc.) registered as LangChain `@tool`s; these call into `dataflows/interface.py` |
| `memory.py` | `FinancialSituationMemory` — Redis-backed agent memory for post-trade reflection |
| `core_stock_tools.py` | Low-level wrappers around stock data |
| `technical_indicators_tools.py` | Low-level wrappers around technical indicators |
| `fundamental_data_tools.py` | Low-level wrappers around fundamental data |
| `news_data_tools.py` | Low-level wrappers around news data |

### `tradingagents/dataflows/`

Market data fetching layer. All agent tools route here; the actual provider is selected at
runtime from the config.

| File | Purpose |
|---|---|
| `config.py` | `get_config()` / `set_config()` — runtime config registry (populated from `DEFAULT_CONFIG` or the user-provided config dict) |
| `interface.py` | Dispatch layer: reads config and calls the right vendor function |
| `y_finance.py` | yfinance implementation for stock data, indicators, fundamentals, news |
| `yfinance_news.py` | yfinance news-specific helpers |
| `alpha_vantage.py` | Alpha Vantage combined entry point |
| `alpha_vantage_stock.py` | AV stock price data |
| `alpha_vantage_indicator.py` | AV technical indicators |
| `alpha_vantage_fundamentals.py` | AV fundamentals (earnings, balance sheet, etc.) |
| `alpha_vantage_news.py` | AV news sentiment |
| `alpha_vantage_common.py` | Shared AV utilities |
| `stockstats_utils.py` | `stockstats` wrapper for computing technical indicators from OHLCV data |
| `utils.py` | General dataflow helpers |

---

## `cli/` — Interactive CLI

Entry point: `tradingagents` (installed script) or `python -m cli.main`.

| File | Purpose |
|---|---|
| `main.py` | Typer app; interactive prompts for ticker, date, provider, models, analysts, depth |
| `config.py` | CLI-specific configuration helpers |
| `models.py` | Provider/model selection menus |
| `stats_handler.py` | LangChain callback handler that tracks token/cost stats and prints a summary table after the run |
| `announcements.py` | Release announcement display |
| `utils.py` | Rich formatting helpers |

---

## `tests/`

| File | What it tests |
|---|---|
| `test_claude_code_client.py` | Unit tests for `ChatClaudeCode`: `_generate`, `bind_tools`, message formatting, tool-call JSON parsing, subprocess error handling — all with mocked `subprocess.run` |
| `test_ticker_symbol_handling.py` | Ticker symbol normalisation / instrument context helpers |

---

## Key Entrypoints

### Programmatic API

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"]    = "claude_code"   # or "openai", "anthropic", etc.
config["deep_think_llm"]  = "claude-opus-4-5"
config["quick_think_llm"] = "claude-sonnet-4-5"

ta = TradingAgentsGraph(
    selected_analysts=["market", "social", "news", "fundamentals"],
    debug=True,
    config=config,
)

final_state, decision = ta.propagate("AAPL", "2026-03-26")
# decision: "BUY" | "OVERWEIGHT" | "HOLD" | "UNDERWEIGHT" | "SELL"
```

### CLI

```bash
tradingagents          # interactive prompts
```

### Smoke test (claude_code provider)

```bash
python test_claude_code_shim.py          # single analyst, fast
FULL_RUN=1 python test_claude_code_shim.py  # all four analysts
```

---

## Data Flow Summary

```
User: ta.propagate("AAPL", "2026-03-26")
  │
  ├─ AgentState initialised with company_of_interest="AAPL", trade_date="2026-03-26"
  │
  ├─ [Analyst nodes]
  │    chain = ChatPromptTemplate | llm.bind_tools([get_stock_data, ...])
  │    chain.invoke(messages) → AIMessage(tool_calls=[...])
  │                          OR AIMessage(content="report text")
  │    ToolNode.invoke(tool_calls) → ToolMessage(content="CSV / JSON data")
  │    (loop until no tool_calls)
  │    → stores report in AgentState (market_report, sentiment_report, etc.)
  │
  ├─ [Researcher debate]
  │    Bull / Bear exchange arguments referencing analyst reports
  │    Research Manager judges → investment_plan
  │
  ├─ [Trader]
  │    Converts investment_plan → trader_investment_plan
  │
  ├─ [Risk debate]
  │    Aggressive / Conservative / Neutral analysts debate risk
  │    Portfolio Manager judges → final_trade_decision
  │
  └─ SignalProcessor.process_signal(final_trade_decision)
       → "BUY" | "OVERWEIGHT" | "HOLD" | "UNDERWEIGHT" | "SELL"
```
