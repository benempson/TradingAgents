"""
End-to-end smoke test: run a single TradingAgents propagation for AAPL
using the Claude Code shim (no ANTHROPIC_API_KEY required).

Usage:
    python test_claude_code_shim.py

Set FULL_RUN=1 in your environment to enable all four analysts instead of
just the market analyst (faster for initial verification).
"""
import os
import signal
import sys
import threading

# ── Guard: shim must work without ANTHROPIC_API_KEY ──────────────────────────
os.environ.pop("ANTHROPIC_API_KEY", None)

# ── Quick sanity-check: is `claude` on PATH? ─────────────────────────────────
import shutil
if shutil.which("claude") is None:
    print("ERROR: 'claude' binary not found on PATH.", file=sys.stderr)
    print("       Install Claude Code and make sure it is authenticated.", file=sys.stderr)
    sys.exit(1)

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ── Timeout safeguard ─────────────────────────────────────────────────────────
TIMEOUT_SECONDS = int("240")  # 4 minutes


def _timeout_handler():
    print(f"\nERROR: Smoke test timed out after {TIMEOUT_SECONDS}s.", file=sys.stderr)
    print("       The graph may be looping. Check tool-call parsing.", file=sys.stderr)
    os._exit(2)

timer = threading.Timer(TIMEOUT_SECONDS, _timeout_handler)
timer.daemon = True
timer.start()

# ── Config ───────────────────────────────────────────────────────────────────
config = DEFAULT_CONFIG.copy()
config["llm_provider"]    = "claude_code"
config["deep_think_llm"]  = "claude-opus-4-5"    # Claude Max — deep thinking
config["quick_think_llm"] = "claude-sonnet-4-5"  # Claude Max — quick thinking
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["max_recur_limit"] = 25   # Lower than default (100) to prevent infinite loops

full_run = os.getenv("FULL_RUN", "").strip() == "1"
analysts = ["market", "social", "news", "fundamentals"] if full_run else ["market"]

print(f"Provider  : claude_code")
print(f"Deep LLM  : {config['deep_think_llm']}")
print(f"Quick LLM : {config['quick_think_llm']}")
print(f"Analysts  : {analysts}")
print(f"Ticker    : AAPL  |  Date: 2026-03-26")
print(f"Timeout   : {TIMEOUT_SECONDS}s  |  Recursion limit: {config['max_recur_limit']}")
print("-" * 60)

# ── Run ───────────────────────────────────────────────────────────────────────
ta = TradingAgentsGraph(
    selected_analysts=analysts,
    debug=True,
    config=config,
)

try:
    final_state, decision = ta.propagate("AAPL", "2026-03-26")
except Exception as exc:
    timer.cancel()
    print(f"\nERROR: Propagation failed: {exc}", file=sys.stderr)
    sys.exit(1)

timer.cancel()

# ── Results ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"DECISION: {decision}")
print("=" * 60)

market_report = final_state.get("market_report", "")
if market_report:
    print(f"\nMarket Report (first 800 chars):\n{market_report[:800]}")

final_decision_text = final_state.get("final_trade_decision", "")
if final_decision_text:
    print(f"\nFull Trade Decision (first 800 chars):\n{final_decision_text[:800]}")

print("\nSmoke test completed successfully.")
