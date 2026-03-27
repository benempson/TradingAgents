# TECHNICAL TESTING STANDARDS

## 1. TEST STRUCTURE & NAMING
### THE STABILITY MANDATE
Tests must not break because of incidental changes (model names, log messages, prompt wording). Target stable, behavioral assertions.

### FIXTURE & PARAMETRIZE NAMING
- Use `pytest.fixture` for shared setup (mock subprocess, sample messages, agent state).
- Use `@pytest.mark.parametrize` for data-driven tests. Name parametrize IDs clearly:
    - *Good:* `@pytest.mark.parametrize("provider", ["openai", "claude_code", "anthropic"])`
    - *Bad:* Unnamed parametrize leading to `test_factory[0]`, `test_factory[1]`

### IMPLEMENTATION PROTOCOL
If you are writing a test and the target behavior has no existing test fixture:
1. **Add to `tests/`:** Locate or create the appropriate test file.
2. **Name fixtures descriptively:** `sample_human_message`, `bound_tools_chat_model`, `mock_subprocess_tool_call`.

## 2. FILE NAMING CONVENTION
- Use `snake_case`.
- **Prefixing:** Use module-level prefixes to prevent collision.
    - *Good:* `test_claude_code_client.py`, `test_trading_graph_propagation.py`
    - *Bad:* `test_client.py` (too generic)
- **Extension:** Always `.py` — no `.tsx` or `.ts` extensions in this project.

## 3. MOCKING PROTOCOLS
### CLEAN MOCKING
- **Tool:** Use `unittest.mock.patch` or `pytest-mock`'s `mocker.patch`.
- **Forbidden:** Do not leave commented-out `mock.patch` calls. If you change strategy, DELETE the old code.
- **subprocess.run mocking:** The primary mock target for `ChatClaudeCode`. Always mock at the module level:
    ```python
    @patch("tradingagents.llm_clients.claude_code_client.subprocess.run")
    def test_generate_text_response(mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Hello world", stderr="")
        ...
    ```

### MOCK RIPPLE AUDIT (ADDING IMPORTS TO MODULES)
When you add a **new import** to a module file, immediately run:
```bash
grep -rl "ModuleName" tests/
```
to find every test file that imports or patches that module. Each of those files may need the new import mocked — otherwise they may fail with `AttributeError` or incorrect behavior.

**Procedure:**
1. Add the new import to the module.
2. Grep for all test files that mock or import the module.
3. For each: verify the new import doesn't break existing mocks.
4. Run the full test suite for those files before moving on.

## 4. SUBPROCESS MOCKING (CLAUDE CODE CLIENT SPECIFIC)
The `ChatClaudeCode` class calls `subprocess.run` to invoke the `claude` CLI. Tests for this class MUST:
- Mock `subprocess.run` to avoid real network calls.
- Return a `MagicMock` with `returncode`, `stdout`, and `stderr` attributes.
- Test tool-call JSON responses AND plain text responses as separate test cases.
- Test error responses (`returncode != 0`) to verify `RuntimeError` is raised.

**Standard fixture:**
```python
def make_subprocess_mock(stdout: str, returncode: int = 0):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = ""
    return mock
```

## 5. TEST LOCATION HIERARCHY (THE "COLOCATION" MANDATE)
### PRIORITY 1: EXISTING TEST FILES
- **Rule:** When adding a test case, place it in the existing `test_<module>.py` file first.
- **Reasoning:** Splitting tests fragments the domain knowledge. Keep related tests together.

### PRIORITY 2: NEW PERMANENT FILES
- **Trigger:** You may ONLY create a new file if:
    1. The existing file uses a conflicting mock strategy.
    2. The existing file is excessively large (>500 lines) and you are starting a distinct suite.
- **Protocol:** If you create a new file, it is **Permanent**. Name it architecturally: `test_claude_code_client_integration.py`, never `test_repro.py`.

### THE "LOGIC PERSISTENCE" RULE
- **Forbidden:** You are strictly forbidden from deleting a valid test case once it passes.
- **Consolidation:** If you created a separate file for speed/debugging, MERGE it into the main test file before marking the task done, unless a "Strategy Splitting" trigger applies.

## 6. API CALL ASSERTION PRECISION
When testing a function that calls an external method (`subprocess.run`, a dataflow vendor function, `create_llm_client`, etc.), **never** use a bare `assert mock.called`. These tests are **Category A** and must assert the exact call:

```python
# BAD — does not catch argument regressions
assert mock_subprocess.called

# GOOD — catches model changes, missing flags, wrong argument order
mock_subprocess.assert_called_once_with(
    ["claude", "--print", "--model", "claude-sonnet-4-5",
     "--tools", "", "--no-session-persistence", "--system-prompt", ANY],
    input=ANY,
    capture_output=True,
    text=True,
    encoding="utf-8",
    timeout=120,
)
```

**Rule:** When you encounter a loose `assert mock.called` for an external method during any spec update, strengthen it to `assert_called_once_with(...)` in the same pass — do not defer it.

## 7. THE "BORN PERMANENT" PROTOCOL (ALL FILE TYPES)
- **Scope:** Applies to test files, source modules, and utilities.
- **Creation:** Never create a file intended to be deleted later. Name it correctly from the start.
    - *Bad:* `test_bug.py`, `test_temp.py`
    - *Good:* `test_claude_code_client.py`, `test_graph_signal_processing.py`
- **Refactoring Artifacts:** If you create a "reproduction" test, you must be prepared to keep it forever. Name it accordingly.
