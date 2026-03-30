"""TradingAgents Report Renderer.

Converts a final_state dict (or a saved JSON log file) into a polished,
human-readable report in Markdown and/or HTML format.
"""

from tradingagents.reporting.renderer import render_report

__all__ = ["render_report"]
