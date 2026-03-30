# PROJECT_SUMMARY.md — TradingAgents File & Folder Reference
> Last updated: 2026-03-30

## 1. Project Overview

**TradingAgents** is a production-grade multi-agent LLM framework for financial trading analysis. A directed acyclic graph of specialised agents collaborates to produce a final BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL decision for a given ticker and date.

- **Orchestration:** LangGraph (directed acyclic agent graph)
- **LLM abstraction:** LangChain (BaseChatModel, BaseTool, ToolNode)
- **Market data:** yfinance (default), Alpha Vantage
- **Testing:** pytest + unittest.mock (unit); real-call smoke test for E2E
- **CLI:** Typer + Rich
- **Python:** ≥ 3.10

---

## 2. Architecture: The Layer Separation Pattern

The codebase enforces a strict one-way dependency direction:

```
dataflows/  ←  agents/  ←  graph/  →  reporting/
                              ↑
                         llm_clients/
```

### Core Pillars

1. **`dataflows/`** — Market data fetching. No knowledge of agents or the graph. All vendor calls route through `interface.py`, which reads config at runtime to select the active vendor (yfinance or Alpha Vantage).

2. **`agents/`** — Agent node functions. Each exposes a `create_<name>(llm, ...)` factory returning a LangGraph node function (`state -> dict`). Imports from `dataflows/` only.

3. **`llm_clients/`** — LLM provider abstraction. All instantiation flows through `create_llm_client(provider, model, base_url)`. Each provider has a `BaseLLMClient` subclass and a `Normalized*` wrapper that strips reasoning/metadata via `normalize_content()`.

4. **`graph/`** — LangGraph wiring. Constructs the `StateGraph`, adds nodes and edges, and compiles it. Uses both `agents/` and `llm_clients/`. Not imported by any other layer.

5. **`reporting/`** — Presentation layer. Converts a `final_state` dict or JSON log file into Markdown and/or HTML reports with collapsible sections and optional LLM-powered summaries. Pure leaf module — imported by `graph/` and `cli/`, imports nothing from `tradingagents/` except `default_config`.

### Provider Factory

```python
from tradingagents.llm_clients import create_llm_client
client = create_llm_client(provider="claude_code", model="claude-sonnet-4-5")
llm = client.get_llm()  # returns a LangChain BaseChatModel
```

Supported providers: `openai`, `anthropic`, `google`, `xai`, `openrouter`, `ollama`, `claude_code`.

---

## 3. Top-level Layout

```
TradingAgents/
├── tradingagents/          # Core Python package
│   ├── agents/             # All agent node implementations
│   ├── dataflows/          # Market data fetching & caching
│   ├── graph/              # LangGraph wiring, orchestration, I/O
│   ├── llm_clients/        # LLM provider abstraction layer
│   └── reporting/          # Report renderer (Markdown + HTML)
├── screener/               # Standalone technical screener (pre-filter for ta.propagate)
│   ├── screener.py         # CLI entry point + orchestrator
│   ├── discovery.py        # yfinance Screener sector shortlist
│   ├── data_fetcher.py     # IB → Alpha Vantage → yfinance OHLCV fallback chain
│   ├── indicator_engine.py # stockstats indicator computation
│   ├── screening_engine.py # Hard filter + composite score
│   ├── cache_store.py      # TTL-aware Parquet cache
│   └── yf_rate_limiter.py  # Disk-persisted rolling rate counter
├── config/                 # Screener config files (sectors, criteria, watchlists)
│   ├── sectors.json
│   ├── discovery_criteria.json
│   ├── screening_criteria.json
│   └── watchlists/         # One JSON file per curated watchlist
├── cli/                    # Interactive CLI (Typer)
├── tests/                  # Automated unit tests
├── docs/                   # Specs and operational references (created as needed)
│   ├── specs/              # Build plans per feature (docs/specs/<area>/<name>-spec.md)
│   └── refs/               # Operational references (docs/refs/<area>/<name>-ref.md)
├── requirements-screener.txt  # Optional deps for screener (ib_async, pyarrow)
├── main.py                 # Quick example / scratch script
├── test_claude_code_shim.py  # E2E smoke test for the claude_code provider
├── pyproject.toml          # Package metadata & dependencies
├── AGENTS.md               # AI Architectural Manifesto (coding standards, providers, config)
└── PROJECT_SUMMARY.md      # This file
```

---

## 4. `tradingagents/` — Core Package

### `tradingagents/default_config.py`
Single source of truth for all configurable parameters. Always copy before mutating:
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "claude_code"
```

### `tradingagents/llm_clients/`

| File | Purpose |
|---|---|
| `factory.py` | `create_llm_client(provider, model, base_url, **kwargs)` — the single entry point |
| `base_client.py` | `BaseLLMClient` ABC + `normalize_content()` helper that strips reasoning/metadata blocks |
| `openai_client.py` | `NormalizedChatOpenAI` + `OpenAIClient` — handles openai, ollama, openrouter, xai |
| `anthropic_client.py` | `NormalizedChatAnthropic` + `AnthropicClient` |
| `google_client.py` | `NormalizedChatGoogleGenerativeAI` + `GoogleClient` |
| `claude_code_client.py` | `ChatClaudeCode` + `ClaudeCodeClient` — subprocess shim (no API key, uses Claude Max) |
| `validators.py` | `VALID_MODELS` dict + `validate_model()` |

### `tradingagents/graph/`

| File | Purpose |
|---|---|
| `trading_graph.py` | **`TradingAgentsGraph`** — top-level class; `propagate(ticker, date)` runs the analysis |
| `setup.py` | **`GraphSetup`** — constructs the `StateGraph`, adds nodes/edges, compiles |
| `propagation.py` | **`Propagator`** — creates the initial `AgentState` |
| `conditional_logic.py` | **`ConditionalLogic`** — routing functions (`should_continue_market`, `should_continue_debate`, etc.) |
| `signal_processing.py` | **`SignalProcessor`** — extracts BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL from Portfolio Manager output |
| `reflection.py` | **`Reflector`** — post-trade memory update logic |

### `tradingagents/agents/`

#### `agents/analysts/` — Data-gathering (use `quick_think_llm`)

| File | Agent | Tools |
|---|---|---|
| `market_analyst.py` | Market Analyst | `get_stock_data`, `get_indicators` |
| `social_media_analyst.py` | Social Media Analyst | sentiment tools |
| `news_analyst.py` | News Analyst | `get_news`, `get_global_news` |
| `fundamentals_analyst.py` | Fundamentals Analyst | `get_fundamentals`, `get_balance_sheet`, etc. |

#### `agents/researchers/` — Investment thesis (use `quick_think_llm`)

| File | Agent |
|---|---|
| `bull_researcher.py` | Bull Researcher — argues for investment |
| `bear_researcher.py` | Bear Researcher — argues against investment |

#### `agents/managers/` — Decision makers (use `deep_think_llm`)

| File | Agent |
|---|---|
| `research_manager.py` | Research Manager — judges bull/bear debate, produces `investment_plan` |
| `portfolio_manager.py` | Portfolio Manager — judges risk debate, produces `final_trade_decision` |

#### `agents/risk_mgmt/` — Risk debate (use `quick_think_llm`)

| File | Agent |
|---|---|
| `aggressive_debator.py` | Aggressive Analyst |
| `conservative_debator.py` | Conservative Analyst |
| `neutral_debator.py` | Neutral Analyst |

#### `agents/utils/`

| File | Purpose |
|---|---|
| `agent_states.py` | `AgentState`, `InvestDebateState`, `RiskDebateState` TypedDicts |
| `agent_utils.py` | LangChain `@tool`-decorated functions that route into `dataflows/interface.py` |
| `memory.py` | `FinancialSituationMemory` — Redis-backed agent memory for post-trade reflection |

### `tradingagents/reporting/`

| File | Purpose |
|---|---|
| `__init__.py` | Public API: `render_report(state_or_path, output_dir, fmt, summarise, llm)` |
| `renderer.py` | Input normalisation, `ReportData`/`ReportSection` dataclasses, orchestration |
| `summariser.py` | Optional LLM summarisation with per-section error isolation |
| `markdown.py` | Markdown output with `<details>/<summary>` collapsible sections |
| `html.py` | Jinja2-based HTML rendering with responsive CSS |
| `templates/report.html.j2` | Self-contained HTML template (mobile-friendly, signal badges) |

### `tradingagents/dataflows/`

| File | Purpose |
|---|---|
| `config.py` | `get_config()` / `set_config()` — runtime config registry |
| `interface.py` | Dispatch layer: reads config and calls the right vendor function |
| `y_finance.py` | yfinance implementation for stock data, indicators, fundamentals, news |
| `alpha_vantage.py` | Alpha Vantage combined entry point |
| `stockstats_utils.py` | `stockstats` wrapper for computing technical indicators |

---

## 5. Key Entrypoints

### Programmatic API

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"]    = "claude_code"
config["deep_think_llm"]  = "claude-opus-4-5"
config["quick_think_llm"] = "claude-sonnet-4-5"

ta = TradingAgentsGraph(
    selected_analysts=["market", "social", "news", "fundamentals"],
    debug=True,   # constructor param, not a DEFAULT_CONFIG key
    config=config,
)

final_state, decision = ta.propagate("AAPL", "2026-03-26")
# decision: "BUY" | "OVERWEIGHT" | "HOLD" | "UNDERWEIGHT" | "SELL"

# Render report from the just-completed run
ta.render_report(output_dir="./reports", fmt="both", summarise=True)

# Or render from a saved JSON log file (no propagate() needed)
ta.render_report(source="eval_results/AAPL/.../full_states_log_2026-03-26.json", output_dir="./reports")

# Or use the standalone function directly
from tradingagents.reporting import render_report
render_report("eval_results/AAPL/.../full_states_log_2026-03-26.json", "./reports")
```

### CLI

```bash
tradingagents          # interactive prompts
tradingagents report <json_file> [--output-dir DIR] [--format md|html|both] [--summarise]
```

### Technical Screener (pre-filter before deep TA)

```bash
python screener/screener.py [--top-n N] [--date YYYY-MM-DD] [--no-ta]
```

Prompts for sector or watchlist selection, runs OHLCV fetch → indicators → hard filter → composite score, then optionally calls `ta.propagate()` on top-N survivors. See `docs/refs/screener/screener-ref.md` for full operational reference.

### Smoke test (claude_code provider)

```bash
python test_claude_code_shim.py          # single analyst, fast
FULL_RUN=1 python test_claude_code_shim.py  # all four analysts
```

### Unit tests

```bash
python -m pytest tests/
```

---

## 6. Guardrails (from AGENTS.md)

- **The "First, Do No Harm" Rule:** Never delete or disable a failing test to pass a build. Update the test or remove it with justification.
- **No God Modules:** `dataflows/`, `agents/`, `llm_clients/`, and `graph/` must remain strictly separated. No module may import upward in the dependency chain.
- **Normalized Wrappers:** Every new LLM provider MUST have a `Normalized*` subclass that calls `normalize_content()` on `.invoke()` output — no exceptions (except `claude_code` which controls its own output).
- **TDD Mandate:** Logic changes require a failing test before the fix. Config/docs changes do not (see `.ai/rules/09-testing-roi.md`).
- **Subprocess Safety:** `subprocess.run` must always use a list argument. `shell=True` is forbidden.
- **No Hardcoded Credentials:** All API keys come from environment variables.
- **Production-Ready Code:** No `TODO` comments, no `print()` debug statements, no empty `except` blocks in committed code.

---

## 7. Data Flow Summary

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

---

## 8. Operational References (docs/refs/)

Operational references are generated by `/spec-ref` after a feature is implemented. They provide a high-density, maintainer-focused view of each feature's system constants, data model, module map, test coverage, and known edge cases.

```
docs/refs/
└── screener/
    └── screener-ref.md     # Technical Screener — module map, env vars, public API, failure modes, edge cases
```
