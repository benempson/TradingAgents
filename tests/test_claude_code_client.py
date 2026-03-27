"""Unit tests for the Claude Code shim (ChatClaudeCode + ClaudeCodeClient).

All subprocess calls are mocked — no real Claude CLI invocations.
"""
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool

from tradingagents.llm_clients.claude_code_client import (
    ChatClaudeCode,
    ClaudeCodeClient,
    _CLI_SYSTEM_PREAMBLE,
    _build_tool_instructions,
    _extract_first_json_object,
    _extract_text,
    _format_conversation,
    _parse_tool_call,
)


# ── sample tool for bind_tools tests ─────────────────────────────────────────

@tool
def get_stock_data(symbol: str, date: str) -> str:
    """Retrieve historical stock data for a given symbol and date."""
    return f"CSV data for {symbol} on {date}"


@tool
def get_indicators(indicator_name: str) -> str:
    """Retrieve a technical indicator by name."""
    return f"Indicator data for {indicator_name}"


# ── helper function tests ────────────────────────────────────────────────────

class TestExtractText(unittest.TestCase):
    def test_string_passthrough(self):
        self.assertEqual(_extract_text("hello"), "hello")

    def test_list_of_strings(self):
        self.assertEqual(_extract_text(["hello", "world"]), "hello\nworld")

    def test_list_of_typed_blocks(self):
        blocks = [
            {"type": "text", "text": "Analysis:"},
            {"type": "reasoning", "text": "thinking..."},
            {"type": "text", "text": "AAPL is up."},
        ]
        result = _extract_text(blocks)
        self.assertEqual(result, "Analysis:\nAAPL is up.")

    def test_empty_list(self):
        self.assertEqual(_extract_text([]), "")

    def test_non_string_fallback(self):
        self.assertEqual(_extract_text(42), "42")


class TestExtractFirstJsonObject(unittest.TestCase):
    def test_bare_json(self):
        text = '{"type":"tool_use","name":"foo","input":{}}'
        self.assertEqual(_extract_first_json_object(text), text)

    def test_json_with_prose(self):
        text = 'I need to call a tool:\n{"type":"tool_use","name":"foo","input":{}}\nDone.'
        result = _extract_first_json_object(text)
        self.assertIn('"tool_use"', result)

    def test_no_json(self):
        self.assertIsNone(_extract_first_json_object("plain text only"))


class TestParseToolCall(unittest.TestCase):
    def test_valid_tool_call(self):
        text = json.dumps({
            "type": "tool_use",
            "id": "call_abc12345",
            "name": "get_stock_data",
            "input": {"symbol": "AAPL", "date": "2026-03-26"},
        })
        result = _parse_tool_call(text)
        self.assertIsInstance(result, AIMessage)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["name"], "get_stock_data")
        self.assertEqual(result.tool_calls[0]["args"]["symbol"], "AAPL")
        self.assertEqual(result.tool_calls[0]["id"], "call_abc12345")

    def test_tool_call_with_prose_prefix(self):
        text = 'Let me fetch that data:\n' + json.dumps({
            "type": "tool_use",
            "id": "call_def67890",
            "name": "get_indicators",
            "input": {"indicator_name": "rsi"},
        })
        result = _parse_tool_call(text)
        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.tool_calls[0]["name"], "get_indicators")

    def test_not_tool_use_json(self):
        text = '{"type":"result","content":"hello"}'
        result = _parse_tool_call(text)
        self.assertIsNone(result)

    def test_plain_text(self):
        result = _parse_tool_call("AAPL is trading at $200")
        self.assertIsNone(result)

    def test_missing_id_gets_generated(self):
        text = json.dumps({
            "type": "tool_use",
            "name": "get_stock_data",
            "input": {"symbol": "AAPL"},
        })
        result = _parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertTrue(result.tool_calls[0]["id"].startswith("call_"))


class TestFormatConversation(unittest.TestCase):
    def test_basic_human_message(self):
        msgs = [HumanMessage(content="AAPL")]
        result = _format_conversation(msgs)
        self.assertEqual(result, "Human: AAPL")

    def test_system_messages_included_as_prefix(self):
        msgs = [
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Hi"),
        ]
        result = _format_conversation(msgs)
        self.assertIn("[System]: You are helpful", result)
        self.assertIn("Human: Hi", result)

    def test_ai_with_tool_calls(self):
        ai = AIMessage(
            content="",
            tool_calls=[{"name": "get_stock_data", "args": {"symbol": "AAPL"}, "id": "call_1", "type": "tool_call"}],
        )
        msgs = [ai]
        result = _format_conversation(msgs)
        self.assertIn("[Tool call: get_stock_data(", result)
        self.assertIn('"symbol": "AAPL"', result)

    def test_tool_result(self):
        msgs = [ToolMessage(content="CSV data here", tool_call_id="call_1")]
        result = _format_conversation(msgs)
        self.assertIn("[Tool Result]: CSV data here", result)

    def test_full_conversation_round_trip(self):
        msgs = [
            SystemMessage(content="System instructions"),
            HumanMessage(content="Analyze AAPL"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_stock_data", "args": {"symbol": "AAPL"}, "id": "call_1", "type": "tool_call"}],
            ),
            ToolMessage(content="price,date\n200,2026-03-26", tool_call_id="call_1"),
        ]
        result = _format_conversation(msgs)
        self.assertIn("[System]: System instructions", result)
        self.assertIn("Human: Analyze AAPL", result)
        self.assertIn("[Tool call: get_stock_data(", result)
        self.assertIn("[Tool Result]: price,date", result)

    def test_tool_schemas_appended_to_system(self):
        msgs = [
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Analyze"),
        ]
        schemas = [{"type": "function", "function": {"name": "my_tool", "parameters": {}}}]
        result = _format_conversation(msgs, tool_schemas=schemas)
        self.assertIn("[System]: You are helpful", result)
        self.assertIn("my_tool", result)
        self.assertIn("Tool Use Protocol", result)


class TestBuildToolInstructions(unittest.TestCase):
    def test_contains_schema(self):
        schemas = [{"type": "function", "function": {"name": "foo", "parameters": {}}}]
        result = _build_tool_instructions(schemas)
        self.assertIn('"foo"', result)
        self.assertIn("Tool Use Protocol", result)

    def test_preamble_contains_lsp_warning(self):
        self.assertIn("NO LSP tool", _CLI_SYSTEM_PREAMBLE)
        self.assertIn("CRITICAL", _CLI_SYSTEM_PREAMBLE)


# ── ChatClaudeCode tests ─────────────────────────────────────────────────────

class TestChatClaudeCode(unittest.TestCase):
    def test_llm_type(self):
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        self.assertEqual(llm._llm_type, "claude_code")

    def test_bind_tools_returns_new_instance(self):
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        bound = llm.bind_tools([get_stock_data])
        self.assertIsNot(llm, bound)
        self.assertIsNone(llm.bound_tools)
        self.assertIsNotNone(bound.bound_tools)
        self.assertEqual(len(bound.bound_tools), 1)
        self.assertEqual(bound.bound_tools[0]["function"]["name"], "get_stock_data")

    def test_bind_tools_preserves_model_name(self):
        llm = ChatClaudeCode(model_name="claude-opus-4-5")
        bound = llm.bind_tools([get_stock_data, get_indicators])
        self.assertEqual(bound.model_name, "claude-opus-4-5")
        self.assertEqual(len(bound.bound_tools), 2)

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_text_response(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="AAPL is trading at $200 with strong momentum.",
            stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        result = llm._generate([HumanMessage(content="Analyze AAPL")])

        self.assertEqual(len(result.generations), 1)
        msg = result.generations[0].message
        self.assertIsInstance(msg, AIMessage)
        self.assertEqual(msg.content, "AAPL is trading at $200 with strong momentum.")
        self.assertEqual(len(msg.tool_calls), 0)

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_tool_call_response(self, mock_run):
        tool_json = json.dumps({
            "type": "tool_use",
            "id": "call_abc12345",
            "name": "get_stock_data",
            "input": {"symbol": "AAPL", "date": "2026-03-26"},
        })
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=tool_json, stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        bound = llm.bind_tools([get_stock_data])
        result = bound._generate([
            SystemMessage(content="You are a market analyst."),
            HumanMessage(content="Analyze AAPL"),
        ])

        msg = result.generations[0].message
        self.assertEqual(msg.content, "")
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0]["name"], "get_stock_data")
        self.assertEqual(msg.tool_calls[0]["args"]["symbol"], "AAPL")

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_tool_call_with_prose_prefix(self, mock_run):
        tool_json = json.dumps({
            "type": "tool_use",
            "id": "call_xyz99999",
            "name": "get_indicators",
            "input": {"indicator_name": "rsi"},
        })
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=f"I'll fetch the RSI indicator:\n{tool_json}",
            stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        bound = llm.bind_tools([get_indicators])
        result = bound._generate([HumanMessage(content="Get RSI")])

        msg = result.generations[0].message
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0]["name"], "get_indicators")

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_system_in_stdin_not_cli_arg(self, mock_run):
        """System messages go into stdin conversation, not --system-prompt arg."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="OK", stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        llm._generate([
            SystemMessage(content="Be a market analyst"),
            HumanMessage(content="Hi"),
        ])

        # --system-prompt should contain only the short preamble
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--system-prompt")
        system_arg = cmd[idx + 1]
        self.assertEqual(system_arg, _CLI_SYSTEM_PREAMBLE)

        # The actual system message should be in the stdin conversation
        stdin_text = mock_run.call_args.kwargs.get("input", "")
        self.assertIn("[System]: Be a market analyst", stdin_text)
        self.assertIn("Human: Hi", stdin_text)

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_tool_schemas_in_stdin(self, mock_run):
        """Tool schemas go into stdin conversation, not --system-prompt arg."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="OK", stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        bound = llm.bind_tools([get_stock_data])
        bound._generate([
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Analyze"),
        ])

        # --system-prompt is just the short preamble
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--system-prompt")
        self.assertEqual(cmd[idx + 1], _CLI_SYSTEM_PREAMBLE)

        # Tool schemas and instructions in stdin
        stdin_text = mock_run.call_args.kwargs.get("input", "")
        self.assertIn("get_stock_data", stdin_text)
        self.assertIn("Tool Use Protocol", stdin_text)

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_adds_continuation_after_tool_result(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Based on the data, AAPL is bullish.", stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        llm._generate([
            HumanMessage(content="Analyze AAPL"),
            AIMessage(
                content="",
                tool_calls=[{"name": "get_stock_data", "args": {"symbol": "AAPL"}, "id": "call_1", "type": "tool_call"}],
            ),
            ToolMessage(content="price=200", tool_call_id="call_1"),
        ])

        # The conversation input should include a continuation prompt
        input_text = mock_run.call_args[1].get("input") or mock_run.call_args[0][0]
        # input is passed as kwarg
        call_kwargs = mock_run.call_args
        stdin_text = call_kwargs.kwargs.get("input", "")
        self.assertIn("Please provide your analysis based on the tool results above", stdin_text)

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_raises_on_nonzero_exit(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout="", stderr="Authentication failed",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        with self.assertRaises(RuntimeError) as ctx:
            llm._generate([HumanMessage(content="test")])
        self.assertIn("Authentication failed", str(ctx.exception))

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_raises_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5", timeout=120)
        with self.assertRaises(RuntimeError) as ctx:
            llm._generate([HumanMessage(content="test")])
        self.assertIn("timed out", str(ctx.exception))

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_raises_on_missing_cli(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        llm = ChatClaudeCode(cli_path="/nonexistent/claude")
        with self.assertRaises(RuntimeError) as ctx:
            llm._generate([HumanMessage(content="test")])
        self.assertIn("not found", str(ctx.exception))

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_uses_correct_model_flag(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="hello", stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-opus-4-5")
        llm._generate([HumanMessage(content="test")])

        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--model")
        self.assertEqual(cmd[idx + 1], "claude-opus-4-5")

    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_stream_falls_back_to_generate(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="streamed content", stderr="",
        )
        llm = ChatClaudeCode(model_name="claude-sonnet-4-5")
        chunks = list(llm._stream([HumanMessage(content="test")]))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, "streamed content")


# ── ClaudeCodeClient tests ───────────────────────────────────────────────────

class TestClaudeCodeClient(unittest.TestCase):
    def test_get_llm_returns_chat_claude_code(self):
        client = ClaudeCodeClient(model="claude-sonnet-4-5")
        llm = client.get_llm()
        self.assertIsInstance(llm, ChatClaudeCode)
        self.assertEqual(llm.model_name, "claude-sonnet-4-5")

    def test_validate_model_always_true(self):
        client = ClaudeCodeClient(model="any-model-name")
        self.assertTrue(client.validate_model())


# ── factory integration test ─────────────────────────────────────────────────

class TestFactoryIntegration(unittest.TestCase):
    def test_factory_creates_claude_code_client(self):
        from tradingagents.llm_clients.factory import create_llm_client
        client = create_llm_client(provider="claude_code", model="claude-sonnet-4-5")
        self.assertIsInstance(client, ClaudeCodeClient)

    def test_factory_case_insensitive(self):
        from tradingagents.llm_clients.factory import create_llm_client
        client = create_llm_client(provider="Claude_Code", model="claude-opus-4-5")
        self.assertIsInstance(client, ClaudeCodeClient)


if __name__ == "__main__":
    unittest.main()
