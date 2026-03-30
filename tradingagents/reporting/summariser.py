"""Optional LLM-powered summarisation for report sections."""

import logging
from typing import List

from tradingagents.reporting.renderer import (
    ReportData,
    ReportSection,
    SUMMARY_FALLBACK,
    SECTION_NOT_INCLUDED,
)

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

_MAX_PARAGRAPH_LEN = 500


def _extract_first_paragraph(content: str) -> str:
    """Extract the first non-empty paragraph from content.

    Splits on double newlines and returns the first paragraph that contains
    non-whitespace text. Truncates to ~500 characters with '...' if longer.

    Args:
        content: Raw section content string.

    Returns:
        First paragraph text, possibly truncated, or empty string.
    """
    if not content or not content.strip():
        return ""

    paragraphs = content.split("\n\n")
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if stripped:
            if len(stripped) > _MAX_PARAGRAPH_LEN:
                return stripped[:_MAX_PARAGRAPH_LEN] + "..."
            return stripped

    return ""


# ── internal ─────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a concise financial report summariser. "
    "Produce a 2-4 sentence summary of the following report section. "
    "Focus on the key findings, signals, and actionable conclusions. "
    "Do not add any preamble or labels -- return only the summary text."
)


def _all_sections(report_data: ReportData) -> List[ReportSection]:
    """Collect every ReportSection from the report data in iteration order."""
    sections: List[ReportSection] = list(report_data.analyst_sections)
    sections.extend([
        report_data.bull_history,
        report_data.bear_history,
        report_data.research_manager,
        report_data.trader_plan,
        report_data.aggressive_history,
        report_data.conservative_history,
        report_data.neutral_history,
        report_data.portfolio_manager,
    ])
    return sections


def _apply_first_paragraph_summaries(report_data: ReportData) -> None:
    """Set each included section's summary to its first paragraph.

    Used as a zero-cost fallback when no LLM is available.

    Args:
        report_data: The report data to mutate in place.
    """
    for section in _all_sections(report_data):
        if section.included and section.content:
            section.summary = _extract_first_paragraph(section.content)


# ── public API ───────────────────────────────────────────────────────────────

def summarise_report(llm, report_data: ReportData) -> None:
    """Generate summaries for each included report section using an LLM.

    If the LLM is None, falls back to first-paragraph extraction. Each
    section is summarised independently -- a failure on one does not affect
    others.

    Args:
        llm: A LangChain BaseChatModel instance, or None for fallback mode.
        report_data: The report data to mutate in place (sets section.summary).
    """
    if llm is None:
        logger.warning(
            "Summarisation requested but no LLM instance provided; skipping summaries."
        )
        _apply_first_paragraph_summaries(report_data)
        return

    for section in _all_sections(report_data):
        if not section.included or not section.content:
            continue

        try:
            result = llm.invoke([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "human", "content": section.content},
            ])
            section.summary = result.content
        except Exception:
            logger.warning(
                "Summarisation failed for section '%s'",
                section.title,
                exc_info=True,
            )
            section.summary = SUMMARY_FALLBACK
