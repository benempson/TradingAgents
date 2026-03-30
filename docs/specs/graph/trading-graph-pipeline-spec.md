# Trading Graph Pipeline
**Status:** IMPLEMENTED
**Created:** 2026-03-30

## 1. Context & Goal

TradingAgents needs a single orchestration entry point that:

1. Accepts a **ticker symbol** and a **trade date**.
2. Runs a configurable pipeline of LLM-powered analyst, researcher, trader, and risk-management agents via a LangGraph `StateGraph`.
3. Produces a final trading decision (one of `BUY | OVERWEIGHT | HOLD | UNDERWEIGHT | SELL`).
4. Optionally reflects on past decisions to improve future performance via memory.

The user-facing API is `TradingAgentsGraph` (instantiated in `main.py`), with two primary methods: `propagate(ticker, date)` and `reflect_and_remember(returns)`.

## 2. Requirements (The "What")

### 2.1 Configuration

- [x] REQ-CFG-01: Accept a `config` dict at init; fall back to `DEFAULT_CONFIG` when `None`.
- [x] REQ-CFG-02: Support `llm_provider`, `deep_think_llm`, `quick_think_llm`, `backend_url`, and provider-specific thinking kwargs (`google_thinking_level`, `openai_reasoning_effort`, `anthropic_effort`).
- [x] REQ-CFG-03: Support `data_vendors` (category-level) and `tool_vendors` (tool-level override) for market data routing.
- [x] REQ-CFG-04: Expose `max_debate_rounds` and `max_risk_discuss_rounds` to control loop iterations.
- [x] REQ-CFG-05: Expose `max_recur_limit` as LangGraph recursion guard.
- [x] REQ-CFG-06: Propagate config to `tradingagents/dataflows/config.py` via `set_config()` at init time.
- [x] REQ-CFG-07: Accept optional `callbacks` list for LLM/tool stats tracking.

### 2.2 LLM Instantiation

- [x] REQ-LLM-01: Create two LLM tiers (`deep_thinking_llm`, `quick_thinking_llm`) via `create_llm_client()` factory.
- [x] REQ-LLM-02: Pass provider-specific kwargs (thinking level, reasoning effort) only when the matching provider is selected.
- [x] REQ-LLM-03: Forward `callbacks` to the LLM constructor kwargs.

### 2.3 Analyst Selection & Graph Topology

- [x] REQ-GRAPH-01: Accept a `selected_analysts` list (default: `["market", "social", "news", "fundamentals"]`).
- [x] REQ-GRAPH-02: Raise `ValueError` if `selected_analysts` is empty.
- [x] REQ-GRAPH-03: Wire analysts in sequence: first selected analyst connects to `START`; each analyst's `Msg Clear` node connects to the next analyst (or to `Bull Researcher` for the last).
- [x] REQ-GRAPH-04: Each analyst node loops back through its `ToolNode` until no `tool_calls` remain, then transitions to its `Msg Clear` node.

### 2.4 Tool Nodes

- [x] REQ-TOOL-01: `market` tools: `get_stock_data`, `get_indicators`.
- [x] REQ-TOOL-02: `social` tools: `get_news`.
- [x] REQ-TOOL-03: `news` tools: `get_news`, `get_global_news`, `get_insider_transactions`.
- [x] REQ-TOOL-04: `fundamentals` tools: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`.

### 2.5 Debate & Risk Pipeline

- [x] REQ-DEBATE-01: Bull/Bear researchers alternate. Debate ends after `2 * max_debate_rounds` iterations (count tracked in `InvestDebateState.count`).
- [x] REQ-DEBATE-02: Research Manager (deep-think LLM) synthesises the debate into an `investment_plan`.
- [x] REQ-DEBATE-03: Trader converts the investment plan into a `trader_investment_plan`.
- [x] REQ-RISK-01: Three risk analysts (Aggressive, Conservative, Neutral) rotate. Loop ends after `3 * max_risk_discuss_rounds` iterations.
- [x] REQ-RISK-02: Portfolio Manager (deep-think LLM) produces `final_trade_decision`.

### 2.6 Propagation

- [x] REQ-PROP-01: `propagate(ticker, date)` initialises `AgentState` via `Propagator.create_initial_state()`.
- [x] REQ-PROP-02: In debug mode, stream the graph and pretty-print each chunk's last message.
- [x] REQ-PROP-03: In non-debug mode, invoke the graph synchronously.
- [x] REQ-PROP-04: After execution, log the full state to `eval_results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json`.
- [x] REQ-PROP-05: Return `(final_state, processed_signal)` where `processed_signal` is extracted by `SignalProcessor`.

### 2.7 Signal Processing

- [x] REQ-SIG-01: `SignalProcessor.process_signal()` uses the quick-think LLM to extract exactly one of `BUY | OVERWEIGHT | HOLD | UNDERWEIGHT | SELL` from the full decision text.
- [x] REQ-SIG-02: The extraction prompt instructs the LLM to output only the single rating word.

### 2.8 Reflection & Memory

- [x] REQ-REFL-01: `reflect_and_remember(returns_losses)` invokes `Reflector` methods for bull, bear, trader, invest judge, and portfolio manager.
- [x] REQ-REFL-02: Each reflection generates an analysis via the quick-think LLM using a shared reflection system prompt.
- [x] REQ-REFL-03: The reflection result is stored in the corresponding `FinancialSituationMemory` instance via `add_situations()`.

### 2.9 Agent State Shape

- [x] REQ-STATE-01: `AgentState` is a `TypedDict` with fields: `company_of_interest`, `trade_date`, `sender`, `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, `investment_debate_state` (`InvestDebateState`), `investment_plan`, `trader_investment_plan`, `risk_debate_state` (`RiskDebateState`), `final_trade_decision`, `messages` (`MessagesState`).
- [x] REQ-STATE-02: Initial state sets all report fields to empty strings and debate states to zeroed dicts.

## 3. Architecture Plan (The "How")

### Layer compliance: `dataflows <- agents <- graph`

| Component | File | Layer |
|---|---|---|
| `TradingAgentsGraph` | `tradingagents/graph/trading_graph.py` | graph |
| `GraphSetup` | `tradingagents/graph/setup.py` | graph |
| `Propagator` | `tradingagents/graph/propagation.py` | graph |
| `Reflector` | `tradingagents/graph/reflection.py` | graph |
| `SignalProcessor` | `tradingagents/graph/signal_processing.py` | graph |
| `ConditionalLogic` | `tradingagents/graph/conditional_logic.py` | graph |
| Agent factory functions | `tradingagents/agents/` | agents |
| Tool wrappers | `tradingagents/agents/utils/agent_utils.py` | agents |
| Agent state defs | `tradingagents/agents/utils/agent_states.py` | agents |
| Memory | `tradingagents/agents/utils/memory.py` | agents |
| LLM factory | `tradingagents/llm_clients/factory.py` | llm_clients |
| Data interface | `tradingagents/dataflows/interface.py` | dataflows |
| Config | `tradingagents/default_config.py` | top-level |

### Dependency direction

```
main.py  ->  graph/trading_graph.py  ->  graph/{setup, propagation, reflection, ...}
                                     ->  agents/{analysts, researchers, ...}
                                     ->  llm_clients/factory.py
                                     ->  dataflows/config.py (set_config only)
```

No forbidden imports detected.

### Entry point (`main.py`)

`main.py` is a user-facing script (not a library module). It:
1. Loads `.env` via `python-dotenv`.
2. Copies `DEFAULT_CONFIG` and overrides provider, model, and vendor settings.
3. Constructs `TradingAgentsGraph(debug=True, config=config)`.
4. Calls `ta.propagate(ticker, date)` and prints the decision.
5. Optionally calls `ta.reflect_and_remember(returns)` (currently commented out).

## 4. Data Validation (Rule 12)

| Boundary | Validation | Status |
|---|---|---|
| `selected_analysts` empty | `ValueError` raised in `GraphSetup.setup_graph()` | Present |
| Config dict keys | Falls back to `DEFAULT_CONFIG` when `config=None` | Present |
| Provider-specific kwargs | Only passed when provider matches (no stale kwargs leak) | Present |
| Tool return values from LLM | Tools return `str` per LangGraph contract | Present |
| `trade_date` format | Cast to `str(trade_date)` in `Propagator`; no format validation | **Missing** |
| `company_of_interest` | No validation (passed as-is to tools) | **Missing** |
| `SignalProcessor` output | No validation that LLM returned one of the five valid signals | **Missing** |
| `returns_losses` type | No validation in `reflect_and_remember` | **Missing** |

## 5. Testing Strategy (ROI Check)

**Category:** A (logic, state, control flow, LLM orchestration)

### Existing test coverage

| Area | Test file | Status |
|---|---|---|
| `ChatClaudeCode` LLM client | `tests/test_claude_code_client.py` | Covered |
| Screener modules | `tests/test_screener_*.py` | Covered |
| Ticker symbol handling | `tests/test_ticker_symbol_handling.py` | Covered |
| `TradingAgentsGraph.__init__` | None | **Missing** |
| `Propagator.create_initial_state` | None | **Missing** |
| `ConditionalLogic` routing | None | **Missing** |
| `SignalProcessor.process_signal` | None | **Missing** |
| `Reflector` | None | **Missing** |
| `GraphSetup.setup_graph` | None | **Missing** |
| `_log_state` JSON output | None | **Missing** |
| Debug vs non-debug propagation | None | **Missing** |

### Recommended test additions (priority order)

1. `test_conditional_logic.py` -- Pure logic, no LLM mocking needed. Tests debate counting and routing.
2. `test_propagation.py` -- Tests initial state shape and graph args.
3. `test_signal_processing.py` -- Mock LLM, assert extraction prompt and return parsing.
4. `test_trading_graph_init.py` -- Mock `create_llm_client`, assert two-tier LLM setup and provider kwargs.
5. `test_reflection.py` -- Mock LLM, assert each reflection method calls memory correctly.

## 6. Implementation Steps

All steps are marked complete since this is a reverse-engineered spec of existing code.

1. [x] Define `AgentState` TypedDict with debate sub-states.
2. [x] Implement `Propagator` for initial state creation and graph invocation args.
3. [x] Implement `ConditionalLogic` for analyst tool-loop, debate, and risk routing.
4. [x] Implement `GraphSetup` to wire the `StateGraph` from selected analysts through to `Portfolio Manager`.
5. [x] Implement `SignalProcessor` to extract BUY/HOLD/SELL from the final decision.
6. [x] Implement `Reflector` with per-agent memory update.
7. [x] Implement `TradingAgentsGraph` as the public facade orchestrating all components.
8. [x] Create `main.py` as the user-facing entry point.
9. [ ] Add unit tests for `ConditionalLogic`, `Propagator`, `SignalProcessor` (see Section 5).
10. [ ] Add input validation for `trade_date` format and `company_of_interest` (see Section 4).
