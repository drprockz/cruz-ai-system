"""
Tests for ForgeAgent — real implementation with tool_use agentic loop.

ForgeAgent:
  - Defines forge_tools: read_file, write_file, run_linter
  - Runs an internal agentic loop: generate → tool_use → lint → fix → done
  - Executes file I/O and linting in a sandboxed temp directory
  - Never runs code in the project root
  - Returns requires_approval=False (code generation is not irreversible)

RED phase — must fail before production code exists.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput
from agents.forge.forge_agent import ForgeAgent, FORGE_TOOLS


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_text_response(text: str, stop_reason: str = "end_turn") -> MagicMock:
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.content = [MagicMock(type="text", text=text)]
    msg.usage = MagicMock(input_tokens=200, output_tokens=300)
    return msg


def _make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tu_001") -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = tool_name
    block.input = tool_input

    msg = MagicMock()
    msg.stop_reason = "tool_use"
    msg.content = [block]
    msg.usage = MagicMock(input_tokens=150, output_tokens=50)
    return msg


def _make_claude_client(*responses) -> MagicMock:
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return client


def _make_input(task: str = "write a hello world function") -> AgentInput:
    return {
        "task": task,
        "context": {},
        "trace_id": "trace-forge-001",
        "conversation_id": "conv-001",
    }


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestForgeAgentInterface:
    def test_forge_agent_subclasses_base_agent(self):
        from agents.base_agent import BaseAgent
        assert issubclass(ForgeAgent, BaseAgent)

    def test_forge_agent_can_be_instantiated(self):
        assert ForgeAgent() is not None

    def test_forge_agent_name_is_forge(self):
        assert ForgeAgent().name == "FORGE"

    def test_forge_agent_has_process_method(self):
        assert callable(ForgeAgent().process)


# ─────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────

class TestForgeTools:
    def test_forge_tools_is_list(self):
        assert isinstance(FORGE_TOOLS, list)

    def test_forge_tools_not_empty(self):
        assert len(FORGE_TOOLS) >= 3

    def test_each_tool_has_required_keys(self):
        for tool in FORGE_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_read_file_tool_exists(self):
        names = [t["name"] for t in FORGE_TOOLS]
        assert "read_file" in names

    def test_write_file_tool_exists(self):
        names = [t["name"] for t in FORGE_TOOLS]
        assert "write_file" in names

    def test_run_linter_tool_exists(self):
        names = [t["name"] for t in FORGE_TOOLS]
        assert "run_linter" in names

    def test_read_file_schema_has_path(self):
        tool = next(t for t in FORGE_TOOLS if t["name"] == "read_file")
        props = tool["input_schema"]["properties"]
        assert "path" in props

    def test_write_file_schema_has_path_and_content(self):
        tool = next(t for t in FORGE_TOOLS if t["name"] == "write_file")
        props = tool["input_schema"]["properties"]
        assert "path" in props
        assert "content" in props

    def test_run_linter_schema_has_path(self):
        tool = next(t for t in FORGE_TOOLS if t["name"] == "run_linter")
        props = tool["input_schema"]["properties"]
        assert "path" in props


# ─────────────────────────────────────────────
# Simple text response (no tool_use)
# ─────────────────────────────────────────────

class TestForgeSimpleResponse:
    async def test_returns_success_true_for_text(self):
        client = _make_claude_client(_make_text_response("def hello(): return 'world'"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input())

        assert result["success"] is True

    async def test_returns_code_in_result(self):
        code = "def hello():\n    return 'world'"
        client = _make_claude_client(_make_text_response(code))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input())

        assert result["result"] == code

    async def test_agent_name_is_forge(self):
        client = _make_claude_client(_make_text_response("code"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input())

        assert result["agent"] == "FORGE"

    async def test_tracks_tokens_used(self):
        client = _make_claude_client(_make_text_response("code"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input())

        assert result["tokens_used"] == 500  # 200 + 300

    async def test_does_not_require_approval(self):
        client = _make_claude_client(_make_text_response("code"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input())

        assert result["requires_approval"] is False

    async def test_passes_forge_tools_to_claude(self):
        client = _make_claude_client(_make_text_response("code"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            await agent.process(_make_input())

        kwargs = client.messages.create.call_args[1]
        assert "tools" in kwargs
        tool_names = [t["name"] for t in kwargs["tools"]]
        assert "read_file" in tool_names
        assert "write_file" in tool_names


# ─────────────────────────────────────────────
# Tool execution — read_file
# ─────────────────────────────────────────────

class TestForgeReadFileTool:
    async def test_read_file_returns_file_contents(self):
        """When Claude calls read_file, ForgeAgent reads the file and returns contents."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def existing(): pass\n")
            tmp_path = f.name

        try:
            read_resp = _make_tool_use_response("read_file", {"path": tmp_path})
            final_resp = _make_text_response("I've read the file, here's the updated code.")
            client = _make_claude_client(read_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("update the existing function"))

            assert result["success"] is True
            # The tool result should have been fed back to Claude
            assert client.messages.create.call_count == 2
        finally:
            os.unlink(tmp_path)

    async def test_read_file_tool_result_contains_content(self):
        """The tool_result message fed back to Claude must contain the file contents."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# existing code\ndef foo(): pass\n")
            tmp_path = f.name

        try:
            read_resp = _make_tool_use_response("read_file", {"path": tmp_path}, tool_id="tu_read_001")
            final_resp = _make_text_response("Updated code here.")
            client = _make_claude_client(read_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                await agent.process(_make_input("update foo"))

            # Second call should include tool_result with file content
            second_call_messages = client.messages.create.call_args_list[1][1]["messages"]
            messages_str = str(second_call_messages)
            assert "existing code" in messages_str or "foo" in messages_str
        finally:
            os.unlink(tmp_path)

    async def test_read_file_error_on_missing_file(self):
        """Reading a nonexistent file should return an error tool_result, not crash."""
        read_resp = _make_tool_use_response(
            "read_file", {"path": "/nonexistent/path/file.py"}, tool_id="tu_read_err"
        )
        final_resp = _make_text_response("I couldn't read the file.")
        client = _make_claude_client(read_resp, final_resp)
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input("read /nonexistent/path/file.py"))

        # Should NOT crash — error is fed back to Claude as tool_result
        assert result["success"] is True
        second_call_messages = client.messages.create.call_args_list[1][1]["messages"]
        assert any("error" in str(m).lower() or "not found" in str(m).lower()
                   for m in second_call_messages)


# ─────────────────────────────────────────────
# Tool execution — write_file
# ─────────────────────────────────────────────

class TestForgeWriteFileTool:
    async def test_write_file_creates_file(self):
        """When Claude calls write_file, the file should be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "hello.py")
            code = "def hello():\n    return 'world'\n"

            write_resp = _make_tool_use_response(
                "write_file", {"path": target, "content": code}
            )
            final_resp = _make_text_response("File written successfully.")
            client = _make_claude_client(write_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("write hello world to hello.py"))

            assert result["success"] is True
            assert Path(target).exists()
            assert Path(target).read_text() == code

    async def test_write_file_tool_result_confirms_write(self):
        """The tool_result fed back to Claude must confirm success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "out.py")

            write_resp = _make_tool_use_response(
                "write_file", {"path": target, "content": "x = 1\n"}, tool_id="tu_write_001"
            )
            final_resp = _make_text_response("Done.")
            client = _make_claude_client(write_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                await agent.process(_make_input("write x=1 to out.py"))

            second_messages = client.messages.create.call_args_list[1][1]["messages"]
            messages_str = str(second_messages)
            assert "written" in messages_str.lower() or "success" in messages_str.lower()

    async def test_write_file_creates_parent_directories(self):
        """write_file should create parent dirs if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "nested", "deep", "file.py")
            code = "x = 1\n"

            write_resp = _make_tool_use_response(
                "write_file", {"path": target, "content": code}
            )
            final_resp = _make_text_response("Done.")
            client = _make_claude_client(write_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                await agent.process(_make_input("write to nested path"))

            assert Path(target).exists()


# ─────────────────────────────────────────────
# Tool execution — run_linter
# ─────────────────────────────────────────────

class TestForgeRunLinterTool:
    async def test_run_linter_returns_pass_for_clean_code(self):
        """run_linter on valid Python should report pass in the tool_result."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('def hello() -> str:\n    return "world"\n')
            clean_path = f.name

        try:
            lint_resp = _make_tool_use_response(
                "run_linter", {"path": clean_path}, tool_id="tu_lint_001"
            )
            final_resp = _make_text_response("Code looks good!")
            client = _make_claude_client(lint_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("lint the file"))

            second_messages = client.messages.create.call_args_list[1][1]["messages"]
            messages_str = str(second_messages)
            # Either "passed", "clean", "no issues", "success", or "0 errors"
            assert any(kw in messages_str.lower() for kw in
                       ["pass", "clean", "no issue", "success", "0 error", "all clear"])
        finally:
            os.unlink(clean_path)

    async def test_run_linter_returns_errors_for_bad_code(self):
        """run_linter on invalid Python should include error details in tool_result."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # Deliberately invalid Python
            f.write("def bad_function(\n    # missing closing paren and body\n")
            bad_path = f.name

        try:
            lint_resp = _make_tool_use_response(
                "run_linter", {"path": bad_path}, tool_id="tu_lint_002"
            )
            final_resp = _make_text_response("I'll fix the syntax error.")
            client = _make_claude_client(lint_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("lint the bad file"))

            second_messages = client.messages.create.call_args_list[1][1]["messages"]
            messages_str = str(second_messages)
            assert any(kw in messages_str.lower() for kw in
                       ["error", "fail", "syntax", "invalid", "issue"])
        finally:
            os.unlink(bad_path)

    async def test_run_linter_does_not_crash_on_missing_file(self):
        """run_linter on a missing path returns error message, doesn't raise."""
        lint_resp = _make_tool_use_response(
            "run_linter", {"path": "/does/not/exist.py"}, tool_id="tu_lint_003"
        )
        final_resp = _make_text_response("File not found.")
        client = _make_claude_client(lint_resp, final_resp)
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input("lint missing file"))

        assert result["success"] is True  # agent handled it gracefully


# ─────────────────────────────────────────────
# Agentic loop — generate → lint → fix
# ─────────────────────────────────────────────

class TestForgeAgenticLoop:
    async def test_multi_turn_loop_completes(self):
        """Claude calls write_file, then run_linter, then ends — all in one process()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "result.py")
            code = 'def greet(name: str) -> str:\n    return f"Hello, {name}"\n'

            write_resp = _make_tool_use_response(
                "write_file", {"path": target, "content": code}, tool_id="tu_w"
            )
            lint_resp = _make_tool_use_response(
                "run_linter", {"path": target}, tool_id="tu_l"
            )
            final_resp = _make_text_response("Code written and linted. All good.")
            client = _make_claude_client(write_resp, lint_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(
                    _make_input("write a greet function and lint it")
                )

            assert result["success"] is True
            assert client.messages.create.call_count == 3
            assert Path(target).exists()

    async def test_tokens_accumulate_across_loop_turns(self):
        """Tokens from each loop turn are summed in the final AgentOutput."""
        client = _make_claude_client(
            _make_text_response("turn 1 code"),   # 200+300 = 500
        )
        # Override: two turns both returning text (simplified loop)
        write_resp = _make_tool_use_response("write_file", {"path": "/tmp/t.py", "content": "x=1"})
        final_resp = _make_text_response("done")
        client2 = _make_claude_client(write_resp, final_resp)
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client2):
            result = await agent.process(_make_input("write x=1"))

        # Both turns: (150+50) + (200+300) = 700
        assert result["tokens_used"] == 700

    async def test_loop_max_iterations_prevents_infinite_loop(self):
        """
        If Claude keeps calling tools beyond the max, ForgeAgent must stop
        and return what it has rather than looping forever.
        """
        # Create a client that always returns tool_use, never end_turn
        always_tool = _make_tool_use_response("read_file", {"path": "/tmp/x.py"})
        # Side-effect returns the same tool response for each call
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=always_tool)
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input("infinite task"))

        # Must not hang. Result may be success=False or a partial result.
        assert "success" in result
        assert client.messages.create.call_count <= 15  # hard cap


# ─────────────────────────────────────────────
# Error handling
# ─────────────────────────────────────────────

class TestForgeErrorHandling:
    async def test_returns_failure_on_claude_api_error(self):
        import anthropic as ant
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=ant.APIConnectionError(request=MagicMock())
        )
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input("anything"))

        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# Tool: list_directory
# ─────────────────────────────────────────────

class TestForgeListDirectoryTool:
    def test_list_directory_tool_exists_in_forge_tools(self):
        names = [t["name"] for t in FORGE_TOOLS]
        assert "list_directory" in names

    def test_list_directory_schema_has_path(self):
        tool = next(t for t in FORGE_TOOLS if t["name"] == "list_directory")
        assert "path" in tool["input_schema"]["properties"]

    async def test_list_directory_returns_file_listing(self):
        """When Claude calls list_directory, agent returns the directory contents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "alpha.py").write_text("x = 1")
            Path(tmpdir, "beta.py").write_text("y = 2")

            list_resp = _make_tool_use_response(
                "list_directory", {"path": tmpdir}, tool_id="tu_ls_001"
            )
            final_resp = _make_text_response("I see two files.")
            client = _make_claude_client(list_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("list the directory"))

            assert result["success"] is True
            second_messages = client.messages.create.call_args_list[1][1]["messages"]
            messages_str = str(second_messages)
            assert "alpha.py" in messages_str or "beta.py" in messages_str

    async def test_list_directory_error_on_missing_path(self):
        """list_directory on a nonexistent path returns error, doesn't crash."""
        list_resp = _make_tool_use_response(
            "list_directory", {"path": "/nonexistent/dir"}, tool_id="tu_ls_err"
        )
        final_resp = _make_text_response("Directory not found.")
        client = _make_claude_client(list_resp, final_resp)
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
            result = await agent.process(_make_input("list missing dir"))

        assert result["success"] is True
        second_messages = client.messages.create.call_args_list[1][1]["messages"]
        assert any("error" in str(m).lower() or "not found" in str(m).lower()
                   for m in second_messages)

    async def test_list_directory_shows_nested_structure(self):
        """list_directory should indicate subdirectories, not just files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "subdir").mkdir()
            Path(tmpdir, "file.py").write_text("x = 1")

            list_resp = _make_tool_use_response(
                "list_directory", {"path": tmpdir}, tool_id="tu_ls_nested"
            )
            final_resp = _make_text_response("I see a file and a directory.")
            client = _make_claude_client(list_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                await agent.process(_make_input("list the directory"))

            second_messages = client.messages.create.call_args_list[1][1]["messages"]
            messages_str = str(second_messages)
            assert "subdir" in messages_str or "file.py" in messages_str


# ─────────────────────────────────────────────
# Linter — JS/TS support
# ─────────────────────────────────────────────

class TestForgeLinterJSTS:
    async def test_run_linter_on_js_file_does_not_crash(self):
        """run_linter on a .js file should return a result, not an exception."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write("function hello() { return 'world'; }\n")
            js_path = f.name

        try:
            lint_resp = _make_tool_use_response(
                "run_linter", {"path": js_path}, tool_id="tu_lint_js"
            )
            final_resp = _make_text_response("JS linted.")
            client = _make_claude_client(lint_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("lint the JS file"))

            assert result["success"] is True
            second_messages = client.messages.create.call_args_list[1][1]["messages"]
            # Should get some result back — pass or a message, not an empty string
            assert str(second_messages).strip() != ""
        finally:
            os.unlink(js_path)

    async def test_run_linter_on_ts_file_does_not_crash(self):
        """run_linter on a .ts file should return a result, not an exception."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write("function greet(name: string): string { return `Hello ${name}`; }\n")
            ts_path = f.name

        try:
            lint_resp = _make_tool_use_response(
                "run_linter", {"path": ts_path}, tool_id="tu_lint_ts"
            )
            final_resp = _make_text_response("TS linted.")
            client = _make_claude_client(lint_resp, final_resp)
            agent = ForgeAgent()

            with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client):
                result = await agent.process(_make_input("lint the TS file"))

            assert result["success"] is True
        finally:
            os.unlink(ts_path)


# ─────────────────────────────────────────────
# Agent logging
# ─────────────────────────────────────────────

class TestForgeAgentLogging:
    async def test_forge_calls_self_log_on_success(self):
        """ForgeAgent must log to agent_logs after a successful process()."""
        client = _make_claude_client(_make_text_response("def hello(): pass"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.forge.forge_agent.get_db_service") as mock_get_db, \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        mock_log.assert_called()

    async def test_forge_logs_with_success_status(self):
        """Log call must include status='success' on a successful run."""
        client = _make_claude_client(_make_text_response("def hello(): pass"))
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.forge.forge_agent.get_db_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        call_kwargs = str(mock_log.call_args)
        assert "success" in call_kwargs

    async def test_forge_logs_with_error_status_on_failure(self):
        """Log call must include status='error' when process() raises."""
        import anthropic as ant
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=ant.APIConnectionError(request=MagicMock())
        )
        agent = ForgeAgent()

        with patch("agents.forge.forge_agent.anthropic.AsyncAnthropic", return_value=client), \
             patch("agents.forge.forge_agent.get_db_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            result = await agent.process(_make_input())

        assert result["success"] is False
        mock_log.assert_called()
        assert "error" in str(mock_log.call_args)
