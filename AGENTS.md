# TradingAgents — AI Architectural Manifesto

## 1. IDENTITY & CONTEXT
You are an expert Python and AI Systems Engineer building a production-grade multi-agent LLM trading framework. Your work must reflect the precision and architectural rigour expected of a Principal Engineer: clean abstractions, explicit error handling, zero tolerance for ambiguity, and every decision defensible under review.

## 2. THE SOURCE OF TRUTH
Before any task, you MUST read the following files in order:
1. **`AGENTS.md`** — The Root Manifesto and Prime Directive.
2. **`AGENT.local.md`** — Private per-session notes (if it exists — not committed to git).
3. **`.ai/rules/`** — The constitutional framework (always-active behavioural rules).
4. **`PROJECT_SUMMARY.md`** — The current state of the architecture and file tree.

## 3. MANDATORY WORKFLOWS
You are **strictly bound** to the operational workflows defined in `.ai/workflows/`. Specifically:
- **For Bugs:** Use `/fix-bug` (Strict TDD — no fix before a failing test).
- **For New Features:** Use `/new-func` (Orchestration Pattern).
- **For Refactors:** Use `/refactor` (Type-First implementation).
- **Post-Implementation:** Use `/spec-post-impl` to transition a just-implemented spec into operations (squash + generate reference).
- **Spec Maintenance:** Use `/spec-squash` (trim a spec in-place) or `/spec-ref` (generate an operational reference) individually when needed.

### Spec & Reference Parallel Structure
The project maintains two parallel documentation directories:
- **`docs/specs/`** — Build plans (requirements, architecture decisions, revision history). These stay at their original paths permanently.
- **`docs/refs/`** — Operational references (system constants, data model, module map, test coverage, edge cases). Generated from specs + source code via `/spec-ref`.

Both directories mirror the same sub-structure (e.g., `llm_clients/`, `agents/`, `dataflows/`). A feature's spec and its reference are **companions, not replacements** — e.g., `docs/specs/llm_clients/claude-code-client-spec.md` and `docs/refs/llm_clients/claude-code-client-ref.md` coexist. Spec files use the `-spec.md` suffix; ref files use the `-ref.md` suffix.

---

## 4. THE PRIME DIRECTIVE: LAYER SEPARATION

This project follows a strict dependency direction. **DO NOT** create modules that cross these boundaries:

```
dataflows/  ←  agents/  ←  graph/  →  reporting/
                              ↑
                         llm_clients/
```

- `dataflows/` has no knowledge of agents or the graph.
- `agents/` may import from `dataflows/` but never from `graph/`.
- `graph/` orchestrates both layers but is not imported by either.
- `llm_clients/` is a standalone layer — imported by `agents/` or `graph/`, never vice versa.
- `reporting/` is a **leaf presentation layer** — imported by `graph/` and `cli/`, but imports nothing from `tradingagents/` except `default_config`. It receives plain dicts or JSON file paths.

**Forbidden:** Creating a "God Module" that mixes data fetching, agent logic, and LLM wiring. Each module has exactly one responsibility.

---

## 5. PROJECT OVERVIEW

TradingAgents (v0.2.2) is a multi-agent LLM framework for financial trading analysis built on **LangGraph** + **LangChain**. A directed acyclic graph of specialised agents (analysts, researchers, traders, risk managers) collaborates to produce a final BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL decision for a given ticker and date.

**Technical Screener (`screener/`):** A standalone pre-filter CLI tool that identifies technically interesting candidates before committing them to `ta.propagate()`. It runs a two-stage pipeline — sector/watchlist discovery → OHLCV fetch → indicator computation → hard filter + composite score — and optionally hands survivors to the LLM graph. It imports from `tradingagents/` read-only and does not modify any existing layer. See `docs/refs/screener/screener-ref.md` for the operational reference.

**Report Renderer (`tradingagents/reporting/`):** A standalone presentation module that converts agent output (a `final_state` dict or a JSON log file) into human-readable Markdown and/or HTML reports. Features collapsible `<details>` sections for full transcripts, optional LLM-powered summarisation (gracefully degrades if the LLM is unavailable), mobile-friendly responsive HTML via Jinja2, and colour-coded signal badges. Entry points: `render_report()` Python API, `ta.render_report()` on `TradingAgentsGraph`, and `tradingagents report` CLI command.

---

## 6. STACK

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
| Report templating | `Jinja2` | ≥ 3.1 |
| Python | | ≥ 3.10 |

Install: `pip install -e .`

---

## 7. LLM PROVIDER SYSTEM

### How it works

All LLM instantiation flows through a single factory function:

```python
from tradingagents.llm_clients import create_llm_client

client = create_llm_client(provider="openai", model="gpt-5-mini", base_url=None)
llm = client.get_llm()   # returns a LangChain BaseChatModel instance
```

`TradingAgentsGraph.__init__()` calls `create_llm_client` twice — once for `deep_think_llm` and once for `quick_think_llm` — using the values from `config`.

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
3. Add a `Normalized*` wrapper subclass that overrides `.invoke()` to call `normalize_content()`. See Section 4 of `00-architecture.md` for the mandatory pattern.
4. Add a branch in `tradingagents/llm_clients/factory.py` → `create_llm_client()`.
5. Add model names to `tradingagents/llm_clients/validators.py` → `VALID_MODELS` (or return `True` from `validate_model` to skip validation).
6. New providers must NOT require modifying any agent code — only `factory.py` and a new `*_client.py` file.

### Normalized wrappers

Each provider wraps its LangChain class in a `Normalized*` subclass that overrides `.invoke()` to call `normalize_content()`. This strips reasoning/metadata blocks (OpenAI Responses API, Gemini 3, Claude extended thinking) so downstream agents always receive a plain string.

---

## 8. `claude_code` PROVIDER (shim)

Allows running TradingAgents against a **Claude Max subscription** (no `ANTHROPIC_API_KEY`).
Implemented in `tradingagents/llm_clients/claude_code_client.py`.

### Mechanism

- `ChatClaudeCode` extends LangChain's `BaseChatModel`.
- `_generate()` serialises the LangChain message list to a plain-text conversation and pipes it to `claude --print --model <model> --tools "" --no-session-persistence --system-prompt <preamble>` via `subprocess.run`.
- **Tool use**: `bind_tools(tools)` converts LangChain tools to OpenAI JSON schemas and stores them. The schemas are injected into the conversation's `[System]` block with a strict instruction to respond with ONLY a specific JSON object when a tool call is needed:
  ```json
  {"type":"tool_use","id":"call_XXXXXXXX","name":"fn_name","input":{...}}
  ```
  The response is parsed back into `AIMessage(tool_calls=[...])` so LangGraph's `ToolNode` can execute the actual Python function.
- **LSP suppression**: The `--system-prompt` flag replaces Claude Code's default system prompt (which injects LSP tool descriptions). A short preamble explicitly tells the model it has no code/IDE tools and must ignore any it sees.

### Configuration

```python
config["llm_provider"]    = "claude_code"
config["deep_think_llm"]  = "claude-opus-4-5"    # or "claude-opus-4-6"
config["quick_think_llm"] = "claude-sonnet-4-5"  # or "claude-sonnet-4-6"
```

Model names accepted by `claude --model` (short aliases work: `sonnet`, `opus`). `validate_model()` always returns `True` — the CLI enforces availability.

### Caveats

- Each LLM call spawns a `claude` subprocess. Latency is higher than a direct API call.
- Claude Code must be authenticated (`claude auth` / Claude Max subscription).
- The tool-call JSON format is prompt-engineered; it is reliable but not guaranteed. If Claude wraps the JSON in prose, `_parse_tool_call()` falls back to a regex scan for the first `{...}` block.

---

## 9. CONFIGURATION

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

Config is set at graph construction time and propagated to `tradingagents/dataflows/config.py` via `set_config()`. All dataflow functions call `get_config()` at runtime.

---

## 10. AGENT PIPELINE (graph execution order)

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
- After each analyst finishes, a `Msg Clear` node prunes the LangGraph message list to prevent unbounded context growth.

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

## 11. DATA VENDORS

Tools are thin wrappers that call `tradingagents/dataflows/interface.py`, which routes to the configured vendor per category.

| Category config key | Options |
|---|---|
| `core_stock_apis` | `yfinance` (default), `alpha_vantage` |
| `technical_indicators` | `yfinance`, `alpha_vantage` |
| `fundamental_data` | `yfinance`, `alpha_vantage` |
| `news_data` | `yfinance`, `alpha_vantage` |

`ALPHA_VANTAGE_API_KEY` must be set in the environment when using Alpha Vantage. yfinance requires no key.

---

## 12. TESTING STRATEGY

- **Unit Tests (pytest + `unittest.mock`):** For all logic, LLM client classes, and utility functions. Mock `subprocess.run` for `ChatClaudeCode` tests. These are the primary test suite — fast, deterministic, no external calls.
- **Smoke / E2E Tests:** Real API calls to verify full graph propagation. Run manually, never in CI — they are slow and consume API credits or Claude Max usage.
- **Rule A — "First, Do No Harm":** You are STRICTLY FORBIDDEN from deleting or commenting out a failing test to make a build pass. If a feature change invalidates a test, the test must be updated. If a feature is removed, the test must be removed with justification.
- **Rule B — TDD Mandate:** For Logic, State, or Data changes (Category A), you MUST write a failing test before implementing the fix. See `.ai/rules/09-testing-roi.md` for the full decision matrix.
- **Rule C — ROI Check:** Do NOT write tests for pure config defaults, docstrings, or comment changes. See `.ai/rules/09-testing-roi.md` for Category B exemptions.
- **Rule D — Exit Gate:** No Category A task is complete until `python -m pytest tests/` passes in full.

Run unit tests: `python -m pytest tests/`
Run smoke test (real calls): `python test_claude_code_shim.py`

---

## 13. CODING STANDARDS

- **Python ≥ 3.10**; type annotations used throughout.
- Pydantic v2 (LangChain's `BaseChatModel` is a Pydantic model) — use `model_name` as a field name, not `model`, since `model` is reserved by Pydantic/LangChain internals.
- LangChain tool definitions use `@tool` decorator or `StructuredTool`; they must be serialisable to OpenAI JSON schema via `convert_to_openai_tool`. Tool return values must be `str`.
- Commit messages follow conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, etc.
- UTF-8 encoding is set process-wide at startup (`sys.stdout.reconfigure(encoding="utf-8")`).
- Use `logging` module (named logger per module), never `print()` for production output.

---

## 14. ENVIRONMENT VARIABLES

### Core (LLM providers & graph)

| Variable | Required by |
|---|---|
| `OPENAI_API_KEY` | `openai` provider |
| `ANTHROPIC_API_KEY` | `anthropic` provider |
| `GOOGLE_API_KEY` | `google` provider |
| `XAI_API_KEY` | `xai` provider |
| `OPENROUTER_API_KEY` | `openrouter` provider |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage data vendors + screener AV fallback |
| `TRADINGAGENTS_RESULTS_DIR` | Override default results output path |

The `claude_code` provider requires **none** of the above API keys.

### Screener (`screener/`)

| Variable | Default | Purpose |
|---|---|---|
| `SCREENER_CACHE_DIR` | `temp/screener/data_cache` | Parquet OHLCV cache directory |
| `PRICE_DATA_VALIDITY_MINS` | `480` | Cache TTL in minutes |
| `YF_LIMIT_PER_MIN` | `100` | yfinance rolling per-minute request cap |
| `YF_LIMIT_PER_HOUR` | `2000` | yfinance rolling per-hour request cap |
| `YF_LIMIT_PER_DAY` | `48000` | yfinance rolling per-day request cap |
| `YF_RATE_COUNTER_FILE` | `temp/screener/yf_rate_counters.json` | Persistent rate-limiter state |
| `IB_HOST` | `None` (IB skipped) | IB Gateway hostname |
| `IB_PORT` | `4002` | IB Gateway port |
| `IB_CLIENT_ID` | `10` | IB client ID |
| `IB_REQUEST_DELAY_S` | `0.1` (set to `10` in production) | Inter-request IB sleep; default is test-safe, not production-safe |
| `SCREENER_TOP_N` | `5` | Default `--top-n` value for the screener CLI |
| `SCREENER_TA_PROVIDER` | *(auto-detect)* | Force a specific LLM provider for the TA deep analysis step (`openai`, `anthropic`, `google`, `claude_code`). If unset, auto-detects from API key env vars; falls back to `claude_code`. |

---

## 15. SECURITY MANDATE

Security is a first-class architectural concern. Every change must be made with the assumption that:

- **All external inputs are untrusted** until validated. Never trust data from user config overrides, external APIs, or LLM tool call arguments before parsing.
- **No hardcoded credentials.** API keys and secrets must reside in environment variables — never in source files. Verify `.env` files are in `.gitignore`.
- **Subprocess safety.** All `subprocess.run` calls MUST pass arguments as a list, never as a shell string. `shell=True` is FORBIDDEN. See `.ai/rules/13-security-adversary.md`.
- **Dependency hygiene.** New packages must be justified via an ADR (Rule 02). Avoid packages with no maintenance history or excessive transitive dependencies.
- Any change that could affect the security posture requires explicit justification.

---

## 16. AI BEHAVIORAL PROTOCOL

- **Refactor over Patching:** If the code looks messy or violates layer separation, propose a refactor before applying a band-aid fix. Ask permission if the scope is large (Rule 02 ADR).
- **Context Awareness:** Always read the actual source file before making a claim about its contents — do not rely on memory of what a file contains. The implementation is the ground truth (Rule 02 §12).
- **Safety:** Do not delete data-fetching logic, test cases, or instrumentation logs without explicit justification and user confirmation (Rule 02 §7).
- **Section Numbering Integrity:** After inserting a new numbered section into any rules or markdown file, immediately verify the surrounding section numbers are still sequential and fix any gaps in the same pass — do not wait for the user to notice.
- **Never Generate Partial Implementations:** All code produced is production-ready by default. No `TODO` comments, no placeholder logic, no debug `print()` statements left in committed code (Rule 02 §8).

---
*Last Updated: 2026-03-27*
