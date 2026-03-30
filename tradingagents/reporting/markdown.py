"""Markdown report renderer: converts ReportData into a Markdown document."""

import logging
from typing import List

from tradingagents.reporting.renderer import ReportData, ReportSection, SECTION_NOT_INCLUDED

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────


def _render_section(section: ReportSection) -> str:
    """Render a single ReportSection as Markdown.

    Rules:
    - Not included: show italicised notice, no collapsible.
    - Has summary: show summary text, then full content in a <details> block.
    - No summary: wrap full content in a <details> block for consistency.
    """
    lines: List[str] = []
    lines.append(f"### {section.title}")
    lines.append("")

    if not section.included:
        lines.append(f"*{SECTION_NOT_INCLUDED}*")
        lines.append("")
        return "\n".join(lines)

    if section.summary:
        lines.append(section.summary)
        lines.append("")

    lines.append("<details>")
    lines.append(f"<summary>View full transcript</summary>")
    lines.append("")
    lines.append(section.content)
    lines.append("")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)


# ── public API ───────────────────────────────────────────────────────────────


def render_markdown(report_data: ReportData) -> str:
    """Generate a complete Markdown report document from normalised ReportData.

    Args:
        report_data: Normalised report data containing all sections.

    Returns:
        Complete Markdown document as a string.
    """
    logger.info(
        "Generating Markdown report",
        extra={"ticker": report_data.ticker, "sections": len(report_data.analyst_sections)},
    )

    parts: List[str] = []

    # Header
    parts.append(f"# Trading Analysis Report: {report_data.ticker}")
    parts.append("")
    parts.append(
        f"**Date:** {report_data.trade_date} "
        f"| **Signal:** {report_data.final_signal} "
        f"| **Generated:** {report_data.generated_at}"
    )
    parts.append("")

    if report_data.final_decision_full:
        parts.append("<details>")
        parts.append("<summary>View full decision rationale</summary>")
        parts.append("")
        parts.append(report_data.final_decision_full)
        parts.append("")
        parts.append("</details>")
        parts.append("")

    parts.append("---")
    parts.append("")

    # I. Analyst Reports
    parts.append("## I. Analyst Reports")
    parts.append("")
    for section in report_data.analyst_sections:
        parts.append(_render_section(section))

    # II. Investment Research
    parts.append("## II. Investment Research")
    parts.append("")
    parts.append(_render_section(report_data.bull_history))
    parts.append(_render_section(report_data.bear_history))
    parts.append(_render_section(report_data.research_manager))

    # III. Trading Plan
    parts.append("## III. Trading Plan")
    parts.append("")
    parts.append(_render_section(report_data.trader_plan))

    # IV. Risk Management
    parts.append("## IV. Risk Management")
    parts.append("")
    parts.append(_render_section(report_data.aggressive_history))
    parts.append(_render_section(report_data.conservative_history))
    parts.append(_render_section(report_data.neutral_history))

    # V. Final Decision
    parts.append("## V. Final Decision")
    parts.append("")
    parts.append(_render_section(report_data.portfolio_manager))

    return "\n".join(parts)
