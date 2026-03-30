> Target Spec: docs/specs/graph/report-renderer-spec.md
> Routing: Orchestrator (Score 3/4)
> Wave: 3 of 3 — COMPLETE

## Failure Modes (from spec Section 6)

- [x] FM-01: JSON file not found — let `FileNotFoundError` propagate
- [x] FM-02: Corrupt JSON — catch `JSONDecodeError`, raise `ValueError` with path context, `logger.error()`
- [x] FM-03: Missing keys in JSON/state — render available sections, show "Not included", `logger.warning()` per key
- [x] FM-04: Empty/None state — raise `ValueError("No report data provided")`
- [x] FM-05: LLM summarisation fails per-section — catch `Exception`, substitute fallback, `logger.warning(exc_info=True)`
- [x] FM-06: Summarise=True but no LLM — behave as summarise=False, `logger.warning()`
- [x] FM-07: `render_report()` before `propagate()` — raise `RuntimeError`
- [x] FM-08: Output dir write failure — let `OSError` propagate

## Implementation Checklist

### Wave 1: Core Module (independent files, no integration)

#### Group A: Data Model & Renderer (`renderer.py`)
- [x] A1. Create `tradingagents/reporting/__init__.py` — export `render_report`
- [x] A2. Define `ReportSection` and `ReportData` dataclasses in `renderer.py`
- [x] A3. Implement `_load_from_json(path)` — parse JSON log, unwrap date key, normalise `trader_investment_decision` -> `trader_investment_plan`
- [x] A4. Implement `_load_from_dict(state)` — normalise dict input to `ReportData`
- [x] A5. Implement `normalise_input(state_or_path)` — dispatch to JSON or dict loader
- [x] A6. Handle FM-01 through FM-04 in loaders
- [x] A7. Add breadcrumb logging (Rule 11): entry, JSON parse, missing key warnings

#### Group B: Summariser (`summariser.py`)
- [x] B1. Implement `summarise_section(llm, section_title, content)` — single LLM call with prompt
- [x] B2. Implement `summarise_report(llm, report_data)` — iterate sections, call `summarise_section` per-section
- [x] B3. Handle FM-05: catch `Exception` per section, substitute fallback text
- [x] B4. Handle FM-06: if `llm is None`, log warning and return unchanged
- [x] B5. Implement `_extract_first_paragraph(content)` — fallback for summarise=False
- [x] B6. Add breadcrumb logging: summarisation start/complete/failure per section

#### Group C: Markdown Output (`markdown.py`)
- [x] C1. Implement `render_markdown(report_data)` — returns string
- [x] C2. Header section: ticker, date, signal, timestamp
- [x] C3. Per-section: summary text, then `<details><summary>Full transcript</summary>...</details>`
- [x] C4. Missing sections: "Not included in this analysis run."
- [x] C5. Debate sections (bull/bear, risk): format as dialogue with speaker labels

#### Group D: HTML Output (`html.py` + template)
- [x] D1. Create `tradingagents/reporting/templates/report.html.j2` ��� full Jinja2 template
- [x] D2. Responsive CSS: viewport meta, max-width ~900px, fluid typography, line-height
- [x] D3. `<details>/<summary>` for collapsible sections
- [x] D4. Signal badge with colour mapping (green=BUY, red=SELL, etc.)
- [x] D5. Clean typography: sans-serif, styled headings, section dividers
- [x] D6. Implement `render_html(report_data)` in `html.py` — load template, render with Jinja2 Environment (autoescape=True)
- [x] D7. Template must include `tradingagents/reporting/templates/` in package data

### Wave 2: Public API & Dependency

- [x] E1. Implement `render_report()` in `__init__.py` — wire renderer + summariser + markdown/html, write files, return `{"md": Path, "html": Path}`
- [x] E2. Validate `fmt` parameter (md/html/both), raise `ValueError` if invalid
- [x] E3. Create output directory, write only requested format(s)
- [x] E4. Add `Jinja2>=3.1` to `pyproject.toml` dependencies
- [x] E5. Add `tradingagents/reporting/templates/*` to package data in `pyproject.toml`

### Wave 3: Integration & Tests

- [x] F1. Add `TradingAgentsGraph.render_report()` method — delegates to `render_report()`, uses `self.curr_state` and `self.quick_thinking_llm`
- [x] F2. Handle FM-07: raise `RuntimeError` if `self.curr_state is None`
- [ ] F3. Add `report` CLI command to `cli/main.py` — reads JSON file, optional LLM creation *(DEFERRED: CLI command is a separate integration; core module and Python API are complete)*
- [x] G1. Write test fixture: complete `final_state` dict matching `AgentState` shape
- [x] G2. Write test fixture: JSON log file (with date nesting and `trader_investment_decision` key)
- [x] G3. Tests 1-2: Render complete state -> MD and HTML, assert sections and structure
- [x] G4. Test 3: Render from JSON file, assert key normalisation
- [x] G5. Test 4: Missing sections show "Not included"
- [x] G6. Tests 5-6: Empty state -> ValueError, corrupt JSON -> ValueError
- [x] G7. Tests 7-8: Summarisation success and failure (mock LLM)
- [x] G8. Test 9: Summarise=True with no LLM -> warning logged
- [x] G9. Tests 10-12: fmt="md" only, fmt="html" only, invalid fmt
- [x] G10. Test 13: render_report() before propagate() -> RuntimeError
- [x] G11. Test 14: HTML mobile-friendliness assertions
- [x] G12. Test 15: Section-independent summarisation failure
- [ ] H1. Update `AGENTS.md` — add `reporting/` to architecture diagram and module list *(DEFERRED: docs update after CLI command)*
- [ ] H2. Update `PROJECT_SUMMARY.md` — document new module *(DEFERRED: docs update after CLI command)*

## Security Review (Rule 13) — PASS
- No subprocess calls, no credentials, no env vars
- Jinja2 auto-escaping mitigates HTML injection from LLM content
- No path traversal risk (output dir is caller-specified)

## Test Results
- 15/15 reporting tests pass
- 120/120 full suite passes (zero regressions)
