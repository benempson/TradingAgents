---
description: Scans the codebase to generate a comprehensive architectural summary and file tree.
usage: /document-project
---

# Generate Project Documentation

1.  **Context Gathering (The Stack):**
    -   Read `pyproject.toml` or `setup.py` to identify:
        -   Python version and package name.
        -   Key dependencies (LangChain, LangGraph, yfinance, etc.).
        -   Test framework (pytest).
    -   Read `tradingagents/default_config.py` to capture all `DEFAULT_CONFIG` keys and their defaults.

2.  **Context Gathering (The Rules):**
    -   Read `AGENTS.md` to capture enforced architectural patterns (provider factory, layer separation, etc.).
    -   Read `.ai/rules/00-architecture.md` to catch any active meta-rules.

3.  **Structure Mapping:**
    -   Generate a file tree of the `tradingagents/` directory and `tests/` directory.
    -   **Constraint:** Limit depth to 3 levels to keep it readable.
    -   **Constraint:** Ignore `__pycache__`, `.git`, `.ai`, `*.egg-info`, and `node_modules`.
    -   *Goal:* Visualize the domain grouping (`llm_clients/`, `agents/`, `dataflows/`, `graph/`).

4.  **Deep Dive: The Core Architecture:**
    -   Read `tradingagents/llm_clients/factory.py` to summarize the LLM provider pattern.
    -   Read `tradingagents/llm_clients/base_client.py` to summarize the `BaseLLMClient` interface.
    -   Read `tradingagents/graph/setup.py` to summarize the graph topology and node wiring.
    -   Read `tradingagents/default_config.py` to summarize the configuration system.

5.  **Synthesis & Output:**
    -   Compile all findings into a Markdown report titled `PROJECT_SUMMARY.md`.
    -   **Required Sections:**
        1.  **Project Overview:** Name, purpose, and core stack.
        2.  **Architecture:** Explanation of the layered pattern (dataflows ← agents ← graph).
        3.  **LLM Provider System:** Factory pattern, available providers, `BaseLLMClient` interface.
        4.  **Key Features:** Analyst types, debate system, risk management, portfolio manager.
        5.  **Configuration:** `DEFAULT_CONFIG` key reference.
        6.  **Guardrails:** Summary of the rules in `AGENTS.md`.
        7.  **File Tree:** The generated directory structure.
    -   **Action:** Save this file to the project root.
    -   **Action:** Print the content of the summary to the chat window.
