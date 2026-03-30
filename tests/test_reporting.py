"""Comprehensive tests for the tradingagents.reporting module.

Covers: input normalisation, Markdown rendering, HTML rendering, JSON loading,
summarisation (LLM success/failure/fallback), format selection, and edge cases.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.reporting.renderer import (
    SECTION_NOT_INCLUDED,
    SUMMARY_FALLBACK,
    render_report,
)


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def complete_state():
    """A dict matching the final_state shape with all fields populated."""
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2026-03-27",
        "final_trade_decision": "Based on thorough analysis, our recommendation is BUY.",
        "market_report": "The market shows strong bullish momentum...",
        "sentiment_report": "Social media sentiment is overwhelmingly positive...",
        "news_report": "Recent news indicates strong earnings growth...",
        "fundamentals_report": "P/E ratio is favorable at 18.5...",
        "investment_debate_state": {
            "bull_history": "Bull argues for strong growth trajectory...",
            "bear_history": "Bear cautions about valuation concerns...",
            "history": "...",
            "current_response": "Bull: ...",
            "judge_decision": "The research manager concludes that bullish arguments are stronger...",
            "count": 2,
        },
        "trader_investment_plan": "Allocate 10% of portfolio to AAPL with stop-loss at...",
        "risk_debate_state": {
            "aggressive_history": "Aggressive analyst recommends 15% allocation...",
            "conservative_history": "Conservative analyst suggests 5% allocation...",
            "neutral_history": "Neutral analyst balances both views...",
            "history": "...",
            "latest_speaker": "Neutral",
            "current_aggressive_response": "...",
            "current_conservative_response": "...",
            "current_neutral_response": "...",
            "judge_decision": "Portfolio manager recommends BUY with 8% allocation...",
            "count": 3,
        },
    }


@pytest.fixture()
def json_log_file(tmp_path, complete_state):
    """A JSON log file using the date-keyed envelope with the legacy key name."""
    # The JSON log uses 'trader_investment_decision' instead of 'trader_investment_plan'
    state_copy = dict(complete_state)
    plan_value = state_copy.pop("trader_investment_plan")
    state_copy["trader_investment_decision"] = plan_value

    envelope = {"2026-03-27": state_copy}
    path = tmp_path / "log.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


@pytest.fixture()
def output_dir(tmp_path):
    """Report output directory."""
    return tmp_path / "reports"


# ── section title constants for assertions ──────────────────────────────────

_ALL_SECTION_TITLES = [
    "Market Analysis",
    "Social/Sentiment Analysis",
    "News Analysis",
    "Fundamentals Analysis",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager Synthesis",
    "Trader Investment Plan",
    "Aggressive Analyst",
    "Conservative Analyst",
]


# ── tests ───────────────────────────────────────────────────────────────────


class TestMarkdownRendering:
    """Tests for Markdown output."""

    def test_render_markdown_complete(self, complete_state, output_dir):
        """Rendering complete state to MD produces a file with all sections and <details> tags."""
        result = render_report(complete_state, output_dir, fmt="md")

        assert result["md"] is not None
        assert result["md"].exists()

        # Filename includes ticker and date
        assert "AAPL" in result["md"].name
        assert "2026-03-27" in result["md"].name

        content = result["md"].read_text(encoding="utf-8")

        for title in _ALL_SECTION_TITLES:
            assert title in content, f"Section title '{title}' missing from Markdown output"

        assert "<details>" in content
        assert "</details>" in content


class TestHTMLRendering:
    """Tests for HTML output."""

    def test_render_html_complete(self, complete_state, output_dir):
        """Rendering complete state to HTML produces valid structure with key elements."""
        result = render_report(complete_state, output_dir, fmt="html")

        assert result["html"] is not None
        assert result["html"].exists()

        content = result["html"].read_text(encoding="utf-8")

        assert "<!DOCTYPE html>" in content
        assert "<details>" in content
        assert "</details>" in content
        assert 'name="viewport"' in content

    def test_html_mobile_friendly(self, complete_state, output_dir):
        """HTML output includes viewport meta tag and max-width CSS for responsiveness."""
        result = render_report(complete_state, output_dir, fmt="html")
        content = result["html"].read_text(encoding="utf-8")

        assert 'name="viewport"' in content
        assert "max-width" in content


class TestJSONLoading:
    """Tests for loading from JSON log files."""

    def test_render_from_json_file(self, json_log_file, output_dir):
        """Rendering from a JSON log file normalises keys correctly."""
        result = render_report(str(json_log_file), output_dir, fmt="md")

        content = result["md"].read_text(encoding="utf-8")

        # The legacy key 'trader_investment_decision' should be normalised
        # and the trader plan content should appear in the output
        assert "Allocate 10% of portfolio to AAPL" in content

    def test_corrupt_json_raises(self, tmp_path, output_dir):
        """Invalid JSON raises ValueError with the file path in the message."""
        bad_file = tmp_path / "corrupt.json"
        bad_file.write_text("{not valid json!!!", encoding="utf-8")

        with pytest.raises(ValueError, match=str(bad_file).replace("\\", "\\\\")):
            render_report(str(bad_file), output_dir)


class TestMissingSections:
    """Tests for graceful handling of missing or empty data."""

    def test_missing_sections(self, complete_state, output_dir):
        """Empty or missing report fields produce the 'not included' notice."""
        state = dict(complete_state)
        state["sentiment_report"] = ""
        del state["fundamentals_report"]

        result = render_report(state, output_dir, fmt="md")
        content = result["md"].read_text(encoding="utf-8")

        assert SECTION_NOT_INCLUDED in content

    def test_empty_state_raises(self, output_dir):
        """An empty dict raises ValueError."""
        with pytest.raises(ValueError):
            render_report({}, output_dir)


class TestSummarisation:
    """Tests for LLM-powered summarisation."""

    def test_summarisation_success(self, complete_state, output_dir):
        """When an LLM is provided, its summary text appears in the output."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Summary text here")

        result = render_report(
            complete_state, output_dir, fmt="md", summarise=True, llm=mock_llm
        )
        content = result["md"].read_text(encoding="utf-8")

        assert "Summary text here" in content
        assert mock_llm.invoke.call_count > 0

    def test_summarisation_failure(self, complete_state, output_dir):
        """When LLM raises, fallback text appears but report is still complete."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API error")

        result = render_report(
            complete_state, output_dir, fmt="md", summarise=True, llm=mock_llm
        )
        content = result["md"].read_text(encoding="utf-8")

        assert SUMMARY_FALLBACK in content
        # Report should still contain all section titles
        for title in _ALL_SECTION_TITLES:
            assert title in content

    def test_summarisation_no_llm(self, complete_state, output_dir, caplog):
        """summarise=True with llm=None logs a warning and uses first-paragraph fallback."""
        with caplog.at_level(logging.WARNING, logger="tradingagents.reporting.summariser"):
            result = render_report(
                complete_state, output_dir, fmt="md", summarise=True, llm=None
            )

        content = result["md"].read_text(encoding="utf-8")

        # Report should render without error
        assert result["md"].exists()

        # First paragraph of market_report content should appear as summary text
        # (the first-paragraph fallback extracts leading text)
        assert "The market shows strong bullish momentum" in content

        # A warning should have been logged about missing LLM
        warning_messages = [rec.message for rec in caplog.records if rec.levelno >= logging.WARNING]
        assert any("no LLM instance" in msg for msg in warning_messages), (
            f"Expected warning about missing LLM, got: {warning_messages}"
        )

    def test_section_independent_summarisation_failure(self, complete_state, output_dir):
        """LLM failure on one section does not affect others' summaries."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Transient API failure")
            return MagicMock(content=f"LLM summary for call {call_count}")

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = _side_effect

        result = render_report(
            complete_state, output_dir, fmt="md", summarise=True, llm=mock_llm
        )
        content = result["md"].read_text(encoding="utf-8")

        # The second section should show the fallback
        assert SUMMARY_FALLBACK in content

        # Other sections should have proper LLM summaries
        assert "LLM summary for call 1" in content
        assert "LLM summary for call 3" in content


class TestFormatSelection:
    """Tests for the fmt parameter."""

    def test_format_md_only(self, complete_state, output_dir):
        """fmt='md' produces only a .md file."""
        result = render_report(complete_state, output_dir, fmt="md")

        assert result["md"] is not None
        assert result["md"].exists()
        assert result["md"].suffix == ".md"
        assert result["html"] is None
        assert not list(output_dir.glob("*.html"))

    def test_format_html_only(self, complete_state, output_dir):
        """fmt='html' produces only an .html file."""
        result = render_report(complete_state, output_dir, fmt="html")

        assert result["html"] is not None
        assert result["html"].exists()
        assert result["html"].suffix == ".html"
        assert result["md"] is None
        assert not list(output_dir.glob("*.md"))

    def test_invalid_format_raises(self, complete_state, output_dir):
        """An unsupported format raises ValueError."""
        with pytest.raises(ValueError, match="pdf"):
            render_report(complete_state, output_dir, fmt="pdf")


class TestPrePropagateGuard:
    """Tests for the TradingAgentsGraph.render_report() pre-propagate guard."""

    def test_render_report_before_propagate_no_source(self):
        """TradingAgentsGraph.render_report() raises RuntimeError when no source and no curr_state."""
        with patch(
            "tradingagents.graph.trading_graph.create_llm_client"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.get_llm.return_value = MagicMock()
            mock_factory.return_value = mock_client

            from tradingagents.graph.trading_graph import TradingAgentsGraph

            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.curr_state = None

            with pytest.raises(RuntimeError, match="no source file.*propagate.*not been called"):
                graph.render_report()

    def test_render_report_from_json_without_propagate(self, complete_state, tmp_path):
        """TradingAgentsGraph.render_report(source=...) works without propagate()."""
        # Write a JSON log file
        json_file = tmp_path / "log.json"
        json_file.write_text(json.dumps({"2026-03-27": complete_state}), encoding="utf-8")

        with patch(
            "tradingagents.graph.trading_graph.create_llm_client"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.get_llm.return_value = MagicMock()
            mock_factory.return_value = mock_client

            from tradingagents.graph.trading_graph import TradingAgentsGraph

            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.curr_state = None
            graph.ticker = None
            graph.config = {"results_dir": str(tmp_path / "results")}
            graph.quick_thinking_llm = MagicMock()

            out_dir = tmp_path / "output"
            result = graph.render_report(source=str(json_file), output_dir=str(out_dir))

            assert result["md"] is not None
            assert result["html"] is not None
            assert list(out_dir.glob("*.md"))
            assert list(out_dir.glob("*.html"))
