# Report Renderer
**Status:** IMPLEMENTED (CLI command REQ-API-03 deferred)
**Created:** 2026-03-30

## 1. Context & Goal

After `ta.propagate()` completes, the only persistent output is a raw JSON log at `eval_results/{ticker}/.../full_states_log_{date}.json`. This is not human-readable. The CLI (`cli/main.py`) has its own `save_report_to_disk()` and `display_complete_report()`, but these are tightly coupled to the CLI flow and cannot be used from `main.py` or any other caller.

**Goal:** Create a standalone `tradingagents/reporting/` module that converts a `final_state` dict (or a saved JSON log file) into a polished, human-readable report in both Markdown and HTML formats. The report should present summaries upfront with full transcripts available via collapsible sections.

## 2. Research Summary

### Existing Patterns
- `cli/main.py::save_report_to_disk()` writes per-section `.md` files + a combined `complete_report.md` to `{results_dir}/{ticker}/{date}/reports/`.
- `cli/main.py::display_complete_report()` renders to terminal via Rich panels.
- `trading_graph.py::_log_state()` writes JSON to `eval_results/{ticker}/TradingAgentsStrategy_logs/`.
- Both operate on the `final_state` dict shape (see `AgentState` TypedDict).

### Chosen Approach
New `tradingagents/reporting/` module (Approach B). Sits alongside `graph/`, `agents/`, `dataflows/` as a pure presentation layer. Receives a plain dict -- no imports from `graph/`, `agents/`, or `llm_clients/`.

### Constraints
- Layer direction: `reporting/` must not import from `graph/`, `agents/`, `llm_clients/`, or `dataflows/`.
- **Jinja2** is the templating engine for HTML output (ADR approved 2026-03-30). It provides auto-escaping of LLM-generated content, clean separation of HTML templates from Python logic, and avoids CSS brace-escaping conflicts inherent in f-strings. Added to `pyproject.toml` dependencies.
- `rich` is already available for terminal rendering but is not required by this module (it produces files, not terminal output).
- Summarisation requires an LLM and is strictly optional -- failure must not block report generation.

## 3. Requirements (The "What")

### 3.1 Input Sources

- [x] REQ-IN-01: Accept a `final_state` dict (as returned by `propagate()`) directly.
- [x] REQ-IN-02: Accept a path to a JSON log file (as written by `_log_state()`) and parse it into the same internal shape. The JSON log nests data under a date key; the renderer must unwrap this.
- [x] REQ-IN-03: When loading from JSON, handle the key name difference: JSON uses `trader_investment_decision` while `final_state` uses `trader_investment_plan`. Normalise to a single internal key.

### 3.2 Output Formats

- [x] REQ-OUT-01: Generate a **Markdown** file (`.md`) with collapsible `<details>/<summary>` sections for full transcripts.
- [x] REQ-OUT-02: Generate an **HTML** file (`.html`) with collapsible sections, styled for readability.
- [x] REQ-OUT-03: HTML must be mobile-friendly (responsive viewport meta tag, max-width container, readable font sizes, no horizontal overflow).
- [x] REQ-OUT-04: Both formats written to the same output directory. Default filenames: `report.md` and `report.html`.
- [x] REQ-OUT-05: Output directory defaults to `{results_dir}/{ticker}/{date}/` (using `results_dir` from config or a passed argument). Must be overridable.

### 3.3 Report Structure

Each report contains these sections in order. Every section shows a **summary** (first ~paragraph or a generated synopsis) followed by a collapsible **full transcript**.

- [x] REQ-RPT-01: **Header** -- Ticker, trade date, final signal (BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL), generation timestamp.
- [x] REQ-RPT-02: **Market Analysis** -- from `market_report`.
- [x] REQ-RPT-03: **Social/Sentiment Analysis** -- from `sentiment_report`.
- [x] REQ-RPT-04: **News Analysis** -- from `news_report`.
- [x] REQ-RPT-05: **Fundamentals Analysis** -- from `fundamentals_report`.
- [x] REQ-RPT-06: **Bull vs Bear Debate** -- from `investment_debate_state.bull_history` and `bear_history`. Show as a dialogue/transcript.
- [x] REQ-RPT-07: **Research Manager Synthesis** -- from `investment_debate_state.judge_decision`.
- [x] REQ-RPT-08: **Trader Investment Plan** -- from `trader_investment_plan` (or `trader_investment_decision` in JSON).
- [x] REQ-RPT-09: **Risk Debate** -- from `risk_debate_state.aggressive_history`, `conservative_history`, `neutral_history`. Show as a multi-party dialogue.
- [x] REQ-RPT-10: **Portfolio Manager Final Decision** -- from `risk_debate_state.judge_decision`.

### 3.4 Missing Sections

- [x] REQ-MISS-01: If an analyst was not included in the run (empty string or missing key), the section must display: *"Not included in this analysis run."*
- [x] REQ-MISS-02: Missing sections must not break the report -- all other sections render normally.

### 3.5 Summarisation (Optional, LLM-Powered)

- [x] REQ-SUM-01: When `summarise=True` is passed and an LLM is provided, generate a short summary (2-4 sentences) for each report section. The summary appears above the collapsible full transcript.
- [x] REQ-SUM-02: When `summarise=False` (the default), use the first paragraph of each section's content as the visible preview text. No LLM call is made.
- [x] REQ-SUM-03: The LLM is passed as an optional `BaseChatModel` instance (not created internally). The renderer has no knowledge of providers or config -- it just calls `.invoke()`.
- [x] REQ-SUM-04: If `summarise=True` but the LLM call fails (any exception), catch the error, log a warning, and substitute: *"Summary could not be generated."* The full transcript still renders.
- [x] REQ-SUM-05: If `summarise=True` but no LLM instance was provided (`None`), behave as if `summarise=False` and log a warning.
- [x] REQ-SUM-06: Each section is summarised independently. A failure summarising one section must not affect any other section.

### 3.6 Entry Points

- [x] REQ-API-01: **Python API** -- `tradingagents.reporting.render_report(state_or_path, output_dir, fmt="both", summarise=False, llm=None)`. Returns a dict of `{"md": Path, "html": Path}` for the written files.
- [x] REQ-API-02: **Method on `TradingAgentsGraph`** -- `ta.render_report(output_dir=None, fmt="both", summarise=False)`. Uses `self.curr_state` and `self.quick_thinking_llm` (if summarise is True). Raises `RuntimeError` if called before `propagate()`.
- [ ] REQ-API-03: **CLI command** -- `tradingagents report <json_file> [--output-dir DIR] [--format md|html|both] [--summarise] [--provider PROVIDER] [--model MODEL]`. Reads from a JSON log file. If `--summarise` is passed, creates an LLM client using the provided provider/model (or falls back to defaults from config). *(DEFERRED)*
- [x] REQ-API-04: The `fmt` parameter accepts `"md"`, `"html"`, or `"both"`. Only the requested format(s) are generated.

### 3.7 HTML Specifics

- [x] REQ-HTML-01: Self-contained single HTML file (inline CSS, no external dependencies). Generated from Jinja2 templates with auto-escaping enabled.
- [x] REQ-HTML-02: Responsive design: `<meta name="viewport" content="width=device-width, initial-scale=1">`, max-width container (~900px), fluid typography.
- [x] REQ-HTML-03: Collapsible sections via `<details>/<summary>` elements (native HTML, no JavaScript required).
- [x] REQ-HTML-04: Clean typography: readable serif or sans-serif font, adequate line height, styled headings, subtle section dividers.
- [x] REQ-HTML-05: Signal badge in header -- visually distinct colour for each signal (green for BUY, etc.).

## 4. Architecture Plan (The "How")

### Layer placement

```
dataflows/  <-  agents/  <-  graph/  ->  reporting/
                                          (presentation only)
```

`reporting/` is a **leaf module** -- it is imported by `graph/` (for `ta.render_report()`) and by `cli/` (for the CLI command), but it imports nothing from `tradingagents/` except potentially `default_config` for the `results_dir` default.

### File structure

```
tradingagents/reporting/
    __init__.py          # Public API: render_report()
    renderer.py          # Core logic: parse input, build report data model
    markdown.py          # Markdown output generation
    html.py              # HTML output generation (Jinja2)
    summariser.py        # Optional LLM summarisation
    templates/
        report.html.j2   # Jinja2 HTML template (responsive, mobile-friendly)
```

### Data flow

```
JSON file or final_state dict
        |
        v
   renderer.py          -- normalise input -> ReportData (plain dataclass)
        |
   +----+----+
   |         |
   v         v
markdown.py  html.py    -- format ReportData into output string
   |         |
   v         v
  .md       .html       -- write to output_dir
```

### Integration points

| Caller | Import | What it passes |
|---|---|---|
| `main.py` (user script) | `from tradingagents.reporting import render_report` | `final_state` dict, output path |
| `TradingAgentsGraph.render_report()` | `from tradingagents.reporting import render_report` | `self.curr_state`, `self.quick_thinking_llm` |
| `cli/main.py` (new `report` command) | `from tradingagents.reporting import render_report` | Parsed JSON, optional LLM |

## 5. Data Validation (Rule 12)

| Boundary | Validation | Approach |
|---|---|---|
| JSON file loading | `json.JSONDecodeError` | Catch, raise `ValueError` with context |
| JSON structure | Missing top-level date key, missing nested keys | Graceful: render what exists, show "Not included" for missing |
| `final_state` dict | Missing keys | Same graceful approach as JSON |
| `trader_investment_decision` vs `trader_investment_plan` | Key name mismatch between JSON log and live state | Normalise in `renderer.py`: check both keys |
| `output_dir` | Non-writable path | Let `OSError` propagate (caller's responsibility) |
| `fmt` parameter | Must be `"md"`, `"html"`, or `"both"` | `ValueError` if invalid |
| LLM `.invoke()` response | Unexpected content type | Catch `Exception`, log warning, substitute fallback text |

## 6. Failure Modes

### FM-01: JSON file not found or unreadable
- **Trigger:** Path does not exist or is not a file.
- **Response:** Raise `FileNotFoundError` (standard Python). Do not catch.
- **Log:** None (caller handles).

### FM-02: JSON file is corrupt / not valid JSON
- **Trigger:** `json.loads()` raises `JSONDecodeError`.
- **Response:** Raise `ValueError("Failed to parse JSON log file: {path}: {error}")`.
- **Log:** `logger.error()` with path and error detail.

### FM-03: JSON log has unexpected structure (missing keys)
- **Trigger:** Expected keys like `market_report`, `investment_debate_state` are absent.
- **Response:** Render available sections normally; missing sections show "Not included in this analysis run." No exception raised.
- **Log:** `logger.warning()` for each missing key.

### FM-04: `render_report()` called with empty/None state
- **Trigger:** `state_or_path` is `None` or an empty dict.
- **Response:** Raise `ValueError("No report data provided")`.
- **Log:** None.

### FM-05: LLM summarisation fails for a single section
- **Trigger:** `llm.invoke()` raises any exception (timeout, API error, malformed response).
- **Response:** Catch `Exception`, substitute *"Summary could not be generated."* for that section. Continue rendering all other sections.
- **Log:** `logger.warning("Summarisation failed for section '{section}'", exc_info=True)`.

### FM-06: LLM summarisation requested but no LLM provided
- **Trigger:** `summarise=True` and `llm is None`.
- **Response:** Behave as `summarise=False`. No exception.
- **Log:** `logger.warning("Summarisation requested but no LLM instance provided; skipping summaries.")`.

### FM-07: `TradingAgentsGraph.render_report()` called before `propagate()`
- **Trigger:** `self.curr_state is None`.
- **Response:** Raise `RuntimeError("Cannot render report: propagate() has not been called yet.")`.
- **Log:** None.

### FM-08: Output directory write failure
- **Trigger:** `OSError` when creating directory or writing file.
- **Response:** Let exception propagate to caller.
- **Log:** None (OS error message is sufficient).

## 7. Testing Strategy (ROI Check)

**Category:** A (logic, state transformation, file I/O, LLM integration)

### Test file: `tests/test_reporting.py`

| # | Scenario | Mock | Assertion |
|---|---|---|---|
| 1 | Render from complete `final_state` dict -> MD | None | File written, all 10 sections present, collapsible `<details>` tags |
| 2 | Render from complete `final_state` dict -> HTML | None | File written, valid HTML structure, `<details>` elements, viewport meta |
| 3 | Render from JSON log file | None | JSON parsed, key normalisation (`trader_investment_decision` -> `trader_investment_plan`), same output as dict input |
| 4 | Missing analyst sections | None | "Not included in this analysis run." appears for each missing section |
| 5 | Empty state dict | None | `ValueError` raised |
| 6 | Corrupt JSON file | None | `ValueError` raised with path in message |
| 7 | Summarisation success | Mock LLM `.invoke()` | Summary text appears above collapsible section |
| 8 | Summarisation failure (LLM exception) | Mock LLM `.invoke()` raising `RuntimeError` | "Summary could not be generated." appears; report still complete |
| 9 | Summarisation requested, no LLM | None | Behaves as `summarise=False`; warning logged |
| 10 | `fmt="md"` only | None | Only `.md` file written, no `.html` |
| 11 | `fmt="html"` only | None | Only `.html` file written, no `.md` |
| 12 | Invalid `fmt` value | None | `ValueError` raised |
| 13 | `TradingAgentsGraph.render_report()` before `propagate()` | None | `RuntimeError` raised |
| 14 | HTML mobile-friendliness | None | Assert viewport meta tag and max-width in CSS |
| 15 | Section-independent summarisation failure | Mock LLM: fail on section 2, succeed on others | Only section 2 shows fallback; all others have summaries |

## 8. Implementation Steps

1. [x] Create `tradingagents/reporting/__init__.py` with public `render_report()` signature.
2. [x] Create `tradingagents/reporting/renderer.py` -- input normalisation, `ReportData` dataclass, section extraction logic.
3. [x] Create `tradingagents/reporting/summariser.py` -- optional LLM summarisation with per-section error isolation.
4. [x] Create `tradingagents/reporting/markdown.py` -- Markdown generation with `<details>/<summary>` collapsible sections.
5. [x] Create `tradingagents/reporting/templates/report.html.j2` -- Jinja2 HTML template (responsive CSS, collapsible sections, signal badge).
6. [x] Create `tradingagents/reporting/html.py` -- HTML generation using Jinja2 template rendering with auto-escaping.
7. [x] Add `Jinja2>=3.1` to `pyproject.toml` dependencies.
8. [x] Add `TradingAgentsGraph.render_report()` method to `tradingagents/graph/trading_graph.py`.
9. [ ] Add `report` CLI command to `cli/main.py`. *(DEFERRED)*
10. [x] Write tests in `tests/test_reporting.py` (all 15 scenarios from Section 7).
11. [ ] Update `AGENTS.md` and `PROJECT_SUMMARY.md` to document the new `reporting/` module. *(DEFERRED: after CLI command)*
