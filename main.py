from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "claude_code"
config["deep_think_llm"] = "claude-opus-4-6"
config["quick_think_llm"] = "claude-sonnet-4-6"
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # Options: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # Options: alpha_vantage, yfinance
    "news_data": "yfinance",                 # Options: alpha_vantage, yfinance
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
# _, decision = ta.propagate("2465.HK", "2026-03-27")
# ta.render_report(output_dir="./reports", fmt="both", summarise=True)
# print(decision)

from tradingagents.reporting import render_report
ta.render_report(source=r"F:\Arrayx\Clients\Arrayx\TradingAgents\eval_results\2465.HK\TradingAgentsStrategy_logs\full_states_log_2026-03-27.json", output_dir="./reports", summarise=False)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
