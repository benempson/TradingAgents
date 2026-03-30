"""HTML report renderer using Jinja2 templates."""

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tradingagents.reporting.renderer import ReportData

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).parent / "templates"

SIGNAL_CSS_CLASSES = {
    "BUY": "signal-buy",
    "OVERWEIGHT": "signal-overweight",
    "HOLD": "signal-hold",
    "UNDERWEIGHT": "signal-underweight",
    "SELL": "signal-sell",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_signal_class(signal: str) -> str:
    """Map a final signal string to the corresponding CSS class.

    Handles signals embedded in longer text (e.g. "Final decision: BUY")
    by scanning for known keywords.

    Args:
        signal: The raw final_signal string from ReportData.

    Returns:
        CSS class name for the signal badge.
    """
    upper = signal.upper().strip()
    for keyword, css_class in SIGNAL_CSS_CLASSES.items():
        if keyword in upper:
            return css_class
    return "signal-hold"


# ── public API ───────────────────────────────────────────────────────────────

def render_html(report_data: ReportData) -> str:
    """Render a ReportData instance to a self-contained HTML string.

    Args:
        report_data: Normalised report data from the renderer pipeline.

    Returns:
        Complete HTML document as a string.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")

    signal_class = _get_signal_class(report_data.final_signal)

    logger.info(
        "Rendering HTML report",
        extra={"ticker": report_data.ticker, "signal_class": signal_class},
    )

    return template.render(report=report_data, signal_class=signal_class)
