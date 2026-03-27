# AI BEHAVIORAL PROTOCOLS

## MAJOR CHANGES (ADR REQUIREMENT)
If you suggest a change that involves:
1. Adding a new library/dependency.
2. Changing the LLM provider pattern (e.g., replacing the factory with direct instantiation).
3. Refactoring a file larger than 300 lines.

**YOU MUST STOP** and write a short "Architecture Decision Record" (ADR) justification first.
- List Pros/Cons.
- Explain why the current pattern in `AGENTS.md` is insufficient.
- Wait for user approval before generating code.

### ADR: [Short title]
**Decision:** [What you propose to do]
**Reason current pattern is insufficient:** [Specific constraint or failure mode]
**Pros:** [Bullet list]
**Cons / risks:** [Bullet list]
**Alternatives considered:** [What else was evaluated]

## REFACTORING
If you see "Spaghetti Code" or a file violating the Single Responsibility Principle:
- Do not just patch the bug.
- Propose a refactor to split the logic (e.g., "This module is doing too much, can I extract the data-fetching logic into a separate dataflow?").

## CODE HYGIENE (THE "CLEAN SLATE" RULE)
### 1. NO "JUST IN CASE" COMMENTS
- **Rule:** When refactoring or fixing bugs, **DELETE** the old code. Do not comment it out.
- **Reasoning:** Commented-out code causes context pollution and confuses future AI requests.
- **Safety:** We rely on Git and IDE Undo/Redo for version history, not the file content.

### 2. DESTRUCTIVE REFACTORING
- If you change a strategy (e.g., swapping a mock approach), **overwrite** the previous implementation completely.
- Do not leave "Legacy" or "Old Way" blocks.

### 3. CLEANUP PROTOCOL (PRINT VS LOGGING)
- **Trash:** `print()` statements used for ad-hoc debugging.
    - **Action:** MUST be deleted before finishing a task. These are for your temporary use only.
- **Treasure:** `logger.info()`, `logger.warning()`, `logger.error()` (Python `logging` module).
    - **Action:** MUST be preserved.
    - **Constraint:** Ensure they are implemented according to Rule 11 (Observability) with proper context.

## DOCUMENTATION & COMMENTING STANDARDS
### 1. THE "WHY," NOT THE "WHAT"
- **Forbidden:** Redundant comments that describe syntax (e.g., `i = 0  # set i to zero`).
- **Required:** Comments that explain **Business Logic**, **Edge Cases**, or **Architectural Decisions**.
    - *Good:* `# Must wait for all analysts to complete before starting the researcher debate.`
    - *Good:* `# Using --system-prompt to replace Claude Code's default prompt, which injects LSP tool descriptions.`
- **AI Context:** Write comments assuming that a *future AI session* will read them to understand the *intent* of the code.

### 2. DOCSTRINGS FOR EXPORTS
- All public functions, classes, and modules MUST have a docstring.
- Briefly explain what the function does, its parameters, and return value.
- *Example:*
    ```python
    def create_llm_client(provider: str, model: str, base_url: Optional[str] = None, **kwargs) -> BaseLLMClient:
        """Create an LLM client for the specified provider.

        Args:
            provider: LLM provider name (openai, anthropic, claude_code, etc.)
            model: Model name/identifier.
            base_url: Optional custom API base URL.

        Returns:
            Configured BaseLLMClient instance.

        Raises:
            ValueError: If provider is not supported.
        """
    ```

### 3. VISUAL ORGANIZATION
- In files larger than 100 lines, use comment separators to group logic.
    - `# ── helpers ──────────────────────────────────────────────────────────────────`
    - `# ── main class ───────────────────────────────────────────────────────────────`
    - `# ── provider wrapper ─────────────────────────────────────────────────────────`

## 4. NO MAGIC STRINGS (CONSTANTS)
### THE PROTOCOL
- **Definition:** A "Magic String" is any string literal used in logic comparisons, state updates, or configuration (e.g., `'market'`, `'claude_code'`, `'yfinance'`).
- **Rule:** Magic strings are **STRONGLY DISCOURAGED** in business logic. Use module-level constants or Python enums.

### IMPLEMENTATION
1. **Status/Types:** Use Python `Enum` or module-level `CONSTANT` assignments.
    - *Bad:* `if provider == 'claude_code'`
    - *Good:* `if provider == CLAUDE_CODE_PROVIDER`
2. **Analyst names:** Do not hardcode `"market"`, `"social"`, etc. as bare strings in new logic.
3. **Config keys:** Reference config keys via constants or well-known dict keys documented in `AGENTS.md`.

## 5. THE "ANTI-ASSUMPTION" PROTOCOL
- **The Prime Rule:** If a requirement is ambiguous, you are **STRICTLY FORBIDDEN** from guessing.
- **The "Gap Analysis" Check:** Before generating any plan or code, ask yourself: *"Do I have 100% of the information required to execute this?"*
    - *If No:* Stop. List the missing pieces. Ask the user.
- **Specific Triggers (Stop & Ask):**
    - **Logic:** "What happens if the LLM call fails?" "Is this field optional?" "What does the agent do on timeout?"
    - **Data:** "What format does this tool return?" "Does this dataflow vendor support this API?"
    - **Config:** "Is this a new config key that needs a default in `DEFAULT_CONFIG`?"

### MANDATORY STOP-AND-ASK TRIGGERS
Before writing any implementation code for a new feature, integration point, or async operation, you MUST ask these questions. If the answer is unknown, **STOP** and ask the user:

**Trigger 1 — Failure Mode Coverage:**
> *"What should happen when this fails? I need to know the expected behaviour for: subprocess timeout, LLM API error, empty tool result, missing environment variable, and any background job failure relevant to this feature."*

You may only proceed once each failure mode has a defined fallback behaviour.

**Trigger 2 — Cross-Layer Impact Gate:**
If a change touches more than one architectural layer (dataflows, agents, llm_clients, graph):
> *"Which layers are affected? Does this change respect the dependency direction (dataflows ← agents ← graph)? Am I introducing a forbidden import (e.g., importing a graph-level class inside a dataflow module)?"*

Do not proceed until each affected layer is listed and the dependency direction is confirmed clean.

- **Layered Coverage Rule:** When updating a workflow file, proactively review the corresponding `.ai/rules/` files for the same topic. Workflow files govern *process*; rules files govern *always-active behaviour*. A gap in one often signals a gap in the other.
- **The "Assumption" Label:** If you must make a minor technical assumption, you must explicitly state it:
    > "Assumption: The `trade_date` string is always in YYYY-MM-DD format. Correct?"

## 6. UX-FIRST ERROR RECOVERY EVALUATION
When evaluating fixes for runtime errors during agent execution, consider the full agent pipeline:
- **What state does the pipeline lose?** A restart discards all in-progress analyst reports.
- **Does the fix degrade gracefully?** Prefer solutions that allow the current LangGraph node to succeed over solutions that restart the entire graph.
- **Apply to all "silent recovery" patterns:** state resets and graph reruns all carry a hidden cost.

## 7. DESTRUCTIVE ACTION PROTOCOL (FILE DELETION)
- **The Rule:** Before issuing a file deletion, you MUST output a specific text block in the chat:

    > **⚠️ DELETION REQUEST**
    > **File:** `tradingagents/full/path/to/file.py`
    > **Reason:** [e.g., "Logic merged into claude_code_client.py"]
    > **Status:** [e.g., "Safe to delete (verified merged)"]

- **Timing:** Output this text *immediately before* invoking the tool.

## 8. PRODUCTION-READY MANDATE
All code produced in any workflow is production-ready by default. There are no "placeholder" commits.
- No `print()` debug statements (use `logging` — Rule 11).
- No `TODO` / `FIXME` comments left in place.
- No empty `except` blocks — every `except` must log and either re-raise or return a structured error.
- No hardcoded credentials, API keys, or environment values.
- No `type: ignore` annotations without a comment explaining why.

## 9. WORKFLOW FIRST
Never write implementation code without first invoking the appropriate workflow from `AGENTS.md`. Reading a file, analysing architecture, or asking a clarifying question does not require a workflow. Writing code does.

## 10. REPLACE_ALL IDEMPOTENCY CHECK
Before using `replace_all` (or any bulk find-and-replace), verify that `new_string` does NOT contain `old_string` as a substring.
- **The hazard:** If `new_string` embeds `old_string` (e.g., renaming `agents/` → `tradingagents/agents/`), a second invocation will produce double-prefixes and corrupt every path in the file.
- **The check:** Before issuing the call, ask: *"If this replacement were applied twice, would the result still be correct?"*

## 11. FILE RENAME PROTOCOL
When renaming a tracked file in the repo, always use `git mv` (via `Bash` tool), not a plain file system move. Plain `mv` causes Git to see an untracked add + a deleted file, which loses history.

```bash
git mv tradingagents/llm_clients/old_name.py tradingagents/llm_clients/new_name.py
```

After the rename, update all imports and references and commit everything in one pass.

## 12. SPEC VS IMPLEMENTATION TRUST HIERARCHY
When the spec and the actual implementation file disagree, **the implementation file is the ground truth**. Do not write plans or code based on what the spec says happened — verify against the live file first.
- **Before planning any change:** read the actual file, not just the spec.
- **When a divergence is found:** flag it explicitly to the user ("The spec says X but the actual file does Y — I'll base my plan on the file").
- **Especially important for:** `DEFAULT_CONFIG`, graph topology in `setup.py`, LLM client constructors.
