"""Claude Code shim — routes LLM calls through the `claude --print` CLI.

Uses the authenticated Claude Max subscription (no ANTHROPIC_API_KEY needed).
Tool use is handled by instructing Claude to emit a specific JSON format and
parsing that back into LangChain AIMessage(tool_calls=[...]).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from typing import Any, Dict, Iterator, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from .base_client import BaseLLMClient


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_text(content: Any) -> str:
    """Return plain text from a message content value (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "tool_result":
                    # Nested tool result blocks (Anthropic format in history)
                    parts.append(_extract_text(item.get("content", "")))
        return "\n".join(p for p in parts if p)
    return str(content)


# Short preamble that goes into --system-prompt (replaces Claude Code default
# system prompt, which otherwise injects LSP tool descriptions and confuses the
# model).  Must stay under ~2 KB so it never trips Windows command-line limits.
_CLI_SYSTEM_PREAMBLE = (
    "CRITICAL: You are operating as a data analysis assistant, NOT a code assistant. "
    "You have NO code tools, NO LSP tool, NO bash tool, NO file tools. "
    "IGNORE any IDE, LSP, or code-related tools you may see. "
    "Follow the instructions given to you in the conversation below."
)

_TOOL_USE_INSTRUCTIONS = """
## Tool Use Protocol
When you need to call a function, respond with ONLY this JSON object — no explanation,
no surrounding text, nothing before or after:
{{"type":"tool_use","id":"call_{uid}","name":"<function_name>","input":{{<key>:<value>}}}}

Generate a unique 8-character lowercase hex string for the id each time (e.g. call_3f9a12bc).
After receiving tool results in [Tool Result] blocks, continue your analysis in plain text.
If you have all the information you need and do NOT need to call any tool, respond in plain text.

## Available Functions
{schemas}
"""


def _build_tool_instructions(tool_schemas: List[Dict[str, Any]]) -> str:
    schemas_json = json.dumps(tool_schemas, indent=2)
    uid_placeholder = uuid.uuid4().hex[:8]
    return _TOOL_USE_INSTRUCTIONS.format(uid=uid_placeholder, schemas=schemas_json)


def _format_conversation(
    messages: List[BaseMessage],
    tool_schemas: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Serialise a LangChain message list into a plain-text conversation.

    SystemMessages are included as ``[System]: ...`` blocks (they are NOT
    passed via the ``--system-prompt`` CLI flag because long arguments can
    produce empty responses on Windows).
    """
    lines: List[str] = []

    # ── system messages first ────────────────────────────────────────────
    system_parts: List[str] = [
        _extract_text(m.content) for m in messages if isinstance(m, SystemMessage)
    ]
    if tool_schemas:
        system_parts.append(_build_tool_instructions(tool_schemas))
    if system_parts:
        lines.append("[System]: " + "\n\n".join(system_parts))

    # ── conversation messages ────────────────────────────────────────────
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        elif isinstance(msg, HumanMessage):
            lines.append(f"Human: {_extract_text(msg.content)}")
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = json.dumps(tc.get("args", {}))
                    lines.append(f"Assistant: [Tool call: {tc['name']}({args_str})]")
            elif msg.content:
                lines.append(f"Assistant: {_extract_text(msg.content)}")
        elif isinstance(msg, ToolMessage):
            lines.append(f"[Tool Result]: {_extract_text(msg.content)}")
        else:
            lines.append(f"{type(msg).__name__}: {_extract_text(msg.content)}")
    return "\n\n".join(lines)


def _parse_tool_call(text: str) -> Optional[AIMessage]:
    """Try to extract a tool_use JSON from `text`. Returns None on failure."""
    # First try the full text as-is
    candidate = text.strip()
    for attempt in (candidate, _extract_first_json_object(candidate)):
        if attempt is None:
            continue
        try:
            data = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("type") == "tool_use":
            tool_call = {
                "id": data.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                "name": data["name"],
                "args": data.get("input", {}),
                "type": "tool_call",
            }
            return AIMessage(content="", tool_calls=[tool_call])
    return None


def _extract_first_json_object(text: str) -> Optional[str]:
    """Find the first {...} block in text, even if surrounded by prose."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None


# ── main class ────────────────────────────────────────────────────────────────

class ChatClaudeCode(BaseChatModel):
    """LangChain chat model backed by the `claude --print` CLI.

    Supports tool binding via prompt-engineering: when tools are bound the
    system prompt instructs Claude to respond with a specific JSON format for
    tool calls; the response is parsed back into AIMessage(tool_calls=[...]).
    """

    model_name: str = "claude-sonnet-4-5"
    bound_tools: Optional[List[Dict[str, Any]]] = None
    cli_path: str = "claude"
    timeout: int = 300  # raised from 120; override via CLAUDE_CODE_TIMEOUT env var

    @property
    def _llm_type(self) -> str:
        return "claude_code"

    # LangChain requires this for serialisation
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"model_name": self.model_name, "cli_path": self.cli_path}

    def bind_tools(
        self,
        tools: Sequence[Any],
        **kwargs: Any,
    ) -> "ChatClaudeCode":
        """Return a copy of this model with the given tools bound."""
        schemas = [convert_to_openai_tool(t) for t in tools]
        return self.__class__(
            model_name=self.model_name,
            cli_path=self.cli_path,
            timeout=self.timeout,
            bound_tools=schemas,
        )

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # 1. Build conversation text (includes [System] blocks + tool schemas)
        conversation = _format_conversation(messages, self.bound_tools)

        # 2. If the last message is a ToolMessage, Claude needs a cue to continue
        if messages and isinstance(messages[-1], ToolMessage):
            conversation += (
                "\n\nHuman: Please provide your analysis based on the tool results above."
            )

        # 3. Invoke the claude CLI
        #    --system-prompt is kept SHORT (preamble only) to override Claude
        #    Code's default system prompt (which injects LSP tool descriptions).
        #    The actual analyst instructions go in the conversation via stdin.
        cmd = [
            self.cli_path, "--print",
            "--model", self.model_name,
            "--tools", "",               # disable built-in CC tools (Bash/Edit/Read)
            "--no-session-persistence",  # don't save chat history to disk
            "--system-prompt", _CLI_SYSTEM_PREAMBLE,
        ]

        try:
            proc = subprocess.run(
                cmd,
                input=conversation,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Claude CLI not found at '{self.cli_path}'. "
                "Ensure Claude Code is installed and 'claude' is on PATH."
            ) from None
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Claude CLI timed out after {self.timeout}s. "
                "Consider increasing ChatClaudeCode.timeout."
            ) from None

        if proc.returncode != 0:
            stderr = proc.stderr.strip() if proc.stderr else "(no stderr)"
            raise RuntimeError(
                f"claude --print exited with code {proc.returncode}: {stderr}"
            )

        raw = proc.stdout.strip()

        # 4. Parse response — tool call JSON or plain text
        ai_message: BaseMessage
        if raw and ("{" in raw):
            parsed = _parse_tool_call(raw)
            if parsed is not None:
                ai_message = parsed
            else:
                ai_message = AIMessage(content=raw)
        else:
            ai_message = AIMessage(content=raw)

        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    # ── streaming (not supported; default BaseChatModel raises, we override) ──
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        # Streaming is not needed by TradingAgents; fall back to _generate
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        for gen in result.generations:
            yield AIMessageChunk(content=gen.message.content)


# ── provider wrapper ──────────────────────────────────────────────────────────

class ClaudeCodeClient(BaseLLMClient):
    """BaseLLMClient wrapper for the Claude Code shim."""

    def get_llm(self) -> ChatClaudeCode:
        timeout = int(os.environ.get("CLAUDE_CODE_TIMEOUT", "300"))
        return ChatClaudeCode(model_name=self.model, timeout=timeout)

    def validate_model(self) -> bool:
        # Claude Code manages its own model availability; accept any name
        return True
