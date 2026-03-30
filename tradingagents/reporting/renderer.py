"""Core renderer: input normalisation, data model, and orchestration."""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

VALID_FORMATS = ("md", "html", "both")

SUMMARY_FALLBACK = "Summary could not be generated."
SECTION_NOT_INCLUDED = "Not included in this analysis run."

# Ordered list of report sections with their state keys
VALID_SIGNALS = ("BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL")

SECTION_DEFINITIONS = [
    ("Market Analysis", "market_report"),
    ("Social/Sentiment Analysis", "sentiment_report"),
    ("News Analysis", "news_report"),
    ("Fundamentals Analysis", "fundamentals_report"),
]

# JSON log uses a different key name than the live state dict
_JSON_KEY_ALIASES = {
    "trader_investment_decision": "trader_investment_plan",
}


_SIGNAL_PATTERN = re.compile(
    r"\b(" + "|".join(VALID_SIGNALS) + r")\b",
    re.IGNORECASE,
)


def _extract_signal_keyword(text: str) -> str:
    """Extract the signal keyword (BUY/SELL/HOLD/etc.) from decision text.

    Uses word-boundary matching and returns the LAST match, since the
    final recommendation typically appears at the end of the decision
    text (earlier mentions are often comparisons or rejections like
    "we do not recommend a HOLD").
    """
    matches = _SIGNAL_PATTERN.findall(text)
    if matches:
        return matches[-1].upper()
    return "UNKNOWN"


# ── data model ───────────────────────────────────────────────────────────────

@dataclass
class ReportSection:
    """A single section of the report."""

    title: str
    content: str
    summary: str = ""
    included: bool = True


@dataclass
class ReportData:
    """Normalised report data ready for rendering."""

    ticker: str
    trade_date: str
    final_signal: str  # Extracted keyword: BUY, SELL, HOLD, etc.
    final_decision_full: str = ""  # Full decision text from Portfolio Manager
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Analyst reports
    analyst_sections: List[ReportSection] = field(default_factory=list)

    # Investment debate
    bull_history: ReportSection = field(default_factory=lambda: ReportSection("Bull Researcher", "", included=False))
    bear_history: ReportSection = field(default_factory=lambda: ReportSection("Bear Researcher", "", included=False))
    research_manager: ReportSection = field(default_factory=lambda: ReportSection("Research Manager Synthesis", "", included=False))

    # Trader
    trader_plan: ReportSection = field(default_factory=lambda: ReportSection("Trader Investment Plan", "", included=False))

    # Risk debate
    aggressive_history: ReportSection = field(default_factory=lambda: ReportSection("Aggressive Analyst", "", included=False))
    conservative_history: ReportSection = field(default_factory=lambda: ReportSection("Conservative Analyst", "", included=False))
    neutral_history: ReportSection = field(default_factory=lambda: ReportSection("Neutral Analyst", "", included=False))

    # Portfolio manager
    portfolio_manager: ReportSection = field(default_factory=lambda: ReportSection("Portfolio Manager Decision", "", included=False))


# ── input loading ────────────────────────────────────────────────────────────

def _normalise_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply key aliases (e.g. trader_investment_decision -> trader_investment_plan)."""
    for old_key, new_key in _JSON_KEY_ALIASES.items():
        if old_key in data and new_key not in data:
            data[new_key] = data.pop(old_key)
    return data


def _load_from_json(path: Path) -> Dict[str, Any]:
    """Parse a JSON log file and unwrap the date-keyed envelope.

    The JSON log structure is: {"2026-03-27": {<state fields>}}.
    We take the first (and typically only) date key's value.
    """
    logger.info("Loading report data from JSON file", extra={"path": str(path)})

    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON log file", extra={"path": str(path)}, exc_info=True)
        raise ValueError(f"Failed to parse JSON log file: {path}: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"Failed to parse JSON log file: {path}: expected a non-empty JSON object")

    # Unwrap the date-keyed envelope
    first_key = next(iter(raw))
    state = raw[first_key]
    if not isinstance(state, dict):
        raise ValueError(f"Failed to parse JSON log file: {path}: expected nested object under date key '{first_key}'")

    return _normalise_keys(state)


def _load_from_dict(state: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a final_state dict."""
    logger.info("Loading report data from dict")
    return _normalise_keys(dict(state))


def _make_section(title: str, content: Any) -> ReportSection:
    """Build a ReportSection, marking it as not-included if content is empty."""
    text = str(content) if content else ""
    if not text.strip():
        return ReportSection(title=title, content="", included=False)
    return ReportSection(title=title, content=text, included=True)


def _extract_report_data(state: Dict[str, Any]) -> ReportData:
    """Convert a normalised state dict into a ReportData instance."""
    ticker = state.get("company_of_interest", "UNKNOWN")
    trade_date = state.get("trade_date", "UNKNOWN")
    final_decision_full = state.get("final_trade_decision", "")
    final_signal = _extract_signal_keyword(final_decision_full)

    # Analyst sections
    analyst_sections = []
    for title, key in SECTION_DEFINITIONS:
        content = state.get(key, "")
        section = _make_section(title, content)
        if not section.included:
            logger.warning("Report section missing from state", extra={"section": title, "key": key})
        analyst_sections.append(section)

    # Investment debate
    debate = state.get("investment_debate_state", {})
    if not debate:
        logger.warning("investment_debate_state missing from state")

    bull = _make_section("Bull Researcher", debate.get("bull_history", ""))
    bear = _make_section("Bear Researcher", debate.get("bear_history", ""))
    research_mgr = _make_section("Research Manager Synthesis", debate.get("judge_decision", ""))

    # Trader
    trader = _make_section("Trader Investment Plan", state.get("trader_investment_plan", ""))

    # Risk debate
    risk = state.get("risk_debate_state", {})
    if not risk:
        logger.warning("risk_debate_state missing from state")

    aggressive = _make_section("Aggressive Analyst", risk.get("aggressive_history", ""))
    conservative = _make_section("Conservative Analyst", risk.get("conservative_history", ""))
    neutral = _make_section("Neutral Analyst", risk.get("neutral_history", ""))

    # Portfolio manager
    portfolio = _make_section("Portfolio Manager Decision", risk.get("judge_decision", ""))

    return ReportData(
        ticker=ticker,
        trade_date=trade_date,
        final_signal=final_signal,
        final_decision_full=final_decision_full,
        analyst_sections=analyst_sections,
        bull_history=bull,
        bear_history=bear,
        research_manager=research_mgr,
        trader_plan=trader,
        aggressive_history=aggressive,
        conservative_history=conservative,
        neutral_history=neutral,
        portfolio_manager=portfolio,
    )


def normalise_input(state_or_path: Union[Dict[str, Any], str, Path]) -> ReportData:
    """Load and normalise input from either a dict or a JSON file path.

    Args:
        state_or_path: Either a final_state dict or a path to a JSON log file.

    Returns:
        Normalised ReportData ready for rendering.

    Raises:
        ValueError: If input is empty/None or JSON is malformed.
        FileNotFoundError: If the JSON file path does not exist.
    """
    if state_or_path is None:
        raise ValueError("No report data provided")

    if isinstance(state_or_path, (str, Path)):
        path = Path(state_or_path)
        state = _load_from_json(path)
    elif isinstance(state_or_path, dict):
        if not state_or_path:
            raise ValueError("No report data provided")
        state = _load_from_dict(state_or_path)
    else:
        raise ValueError(f"No report data provided: expected dict or path, got {type(state_or_path).__name__}")

    return _extract_report_data(state)


# ── public API ───────────────────────────────────────────────────────────────

def render_report(
    state_or_path: Union[Dict[str, Any], str, Path],
    output_dir: Union[str, Path],
    fmt: str = "both",
    summarise: bool = False,
    llm: Optional[Any] = None,
) -> Dict[str, Optional[Path]]:
    """Render a trading analysis report from agent state or a JSON log file.

    Args:
        state_or_path: Either a final_state dict (from propagate()) or a path
            to a JSON log file (from _log_state()).
        output_dir: Directory to write the report file(s) to.
        fmt: Output format — "md", "html", or "both".
        summarise: If True and an LLM is provided, generate summaries for
            each section. If the LLM is unavailable or fails, the report
            still renders with fallback text.
        llm: Optional LangChain BaseChatModel instance for summarisation.

    Returns:
        Dict with keys "md" and "html", each mapping to the written Path
        or None if that format was not requested.

    Raises:
        ValueError: If state_or_path is empty/None, JSON is malformed, or fmt is invalid.
        FileNotFoundError: If JSON file path does not exist.
        OSError: If output directory cannot be created or files cannot be written.
    """
    if fmt not in VALID_FORMATS:
        raise ValueError(f"Invalid format '{fmt}': must be one of {VALID_FORMATS}")

    logger.info("Rendering report", extra={"fmt": fmt, "summarise": summarise})

    # 1. Normalise input
    report_data = normalise_input(state_or_path)

    # 2. Optional summarisation
    if summarise:
        from tradingagents.reporting.summariser import summarise_report
        summarise_report(llm, report_data)

    # 3. Generate output(s)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Optional[Path]] = {"md": None, "html": None}

    # Build filename stem: {ticker}_{trade_date} (sanitise for filesystem safety)
    safe_ticker = report_data.ticker.replace("/", "_").replace("\\", "_")
    stem = f"{safe_ticker}_{report_data.trade_date}"

    if fmt in ("md", "both"):
        from tradingagents.reporting.markdown import render_markdown
        md_content = render_markdown(report_data)
        md_path = output_path / f"{stem}.md"
        md_path.write_text(md_content, encoding="utf-8")
        result["md"] = md_path
        logger.info("Markdown report written", extra={"path": str(md_path)})

    if fmt in ("html", "both"):
        from tradingagents.reporting.html import render_html
        html_content = render_html(report_data)
        html_path = output_path / f"{stem}.html"
        html_path.write_text(html_content, encoding="utf-8")
        result["html"] = html_path
        logger.info("HTML report written", extra={"path": str(html_path)})

    return result
