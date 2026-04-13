"""
Tests for QTAgent — test runner and quality gate.

Responsibilities:
  1. Run pytest in a given project directory (asyncio subprocess)
  2. Run npm audit in a given project directory
  3. Generate test code for a given function/module via Qwen 14B
  4. Return success=False when tests fail (so TITAN is blocked)
  5. Return success=True when all tests pass
  6. Never require approval — running tests is non-destructive

Modes (via context["test_type"]):
  "pytest"    — run pytest in context["project_path"]
  "npm_audit" — run npm audit in context["project_path"]
  "generate"  — generate test code for context["code"] via Qwen

Output structure (AgentOutput.result):
  {
    "test_type":       "pytest" | "npm_audit" | "generated",
    "passed":          <int>    (pytest only),
    "failed":          <int>    (pytest only),
    "errors":          <int>    (pytest only),
    "vulnerabilities": <dict>   (npm_audit only: {low, moderate, high, critical}),
    "output":          "<raw runner output>",
    "generated":       "<test code>"  (generate mode only),
  }
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(
    task: str = "Run tests",
    test_type: str = "pytest",
    project_path: str = "/tmp/project",
    code: str = "",
) -> AgentInput:
    ctx: dict = {"test_type": test_type, "project_path": project_path}
    if code:
        ctx["code"] = code
    return {
        "task": task,
        "context": ctx,
        "trace_id": "trace-qt-001",
        "conversation_id": "conv-qt-001",
    }


def _mock_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Return a fake asyncio subprocess process."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


_PYTEST_PASS_OUTPUT = b"""
============================= test session starts ==============================
PASSED tests/test_auth.py::test_login
PASSED tests/test_auth.py::test_register
============================== 2 passed in 0.42s ===============================
"""

_PYTEST_FAIL_OUTPUT = b"""
============================= test session starts ==============================
PASSED tests/test_auth.py::test_login
FAILED tests/test_auth.py::test_register - AssertionError: expected 201
============================== 1 passed, 1 failed in 0.55s =====================
"""

_PYTEST_ERROR_OUTPUT = b"""
============================= test session starts ==============================
ERROR tests/test_broken.py - ModuleNotFoundError: No module named 'xyz'
============================ 1 error in 0.12s ==================================
"""

_NPM_AUDIT_CLEAN = json.dumps({
    "metadata": {
        "vulnerabilities": {
            "info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0,
            "total": 0,
        }
    }
}).encode()

_NPM_AUDIT_VULNS = json.dumps({
    "metadata": {
        "vulnerabilities": {
            "info": 0, "low": 2, "moderate": 1, "high": 1, "critical": 0,
            "total": 4,
        }
    }
}).encode()


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestQTAgentInterface:
    def test_qt_agent_can_be_imported(self):
        from agents.qt.qt_agent import QTAgent  # noqa: F401

    def test_qt_agent_extends_base_agent(self):
        from agents.qt.qt_agent import QTAgent
        assert issubclass(QTAgent, BaseAgent)

    def test_qt_agent_name_is_QT(self):
        from agents.qt.qt_agent import QTAgent
        assert QTAgent().name == "QT"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.qt.qt_agent import QTAgent
        with patch("agents.qt.qt_agent.get_db_service"):
            coro = QTAgent().process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()

    def test_parse_pytest_output_is_exported(self):
        from agents.qt.qt_agent import _parse_pytest_output  # noqa: F401

    def test_parse_npm_audit_output_is_exported(self):
        from agents.qt.qt_agent import _parse_npm_audit_output  # noqa: F401


# ─────────────────────────────────────────────
# Pytest runner
# ─────────────────────────────────────────────

class TestQTAgentPytest:
    async def test_returns_success_true_when_all_tests_pass(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["success"] is True

    async def test_returns_success_false_when_tests_fail(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=1, stdout=_PYTEST_FAIL_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["success"] is False

    async def test_passed_count_parsed_correctly(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["result"]["passed"] == 2

    async def test_failed_count_parsed_correctly(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=1, stdout=_PYTEST_FAIL_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["result"]["failed"] == 1

    async def test_error_count_parsed_from_error_output(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=2, stdout=_PYTEST_ERROR_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["result"]["errors"] >= 1

    async def test_pytest_run_in_project_path(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc) as mock_exec, \
             patch("agents.qt.qt_agent.get_db_service"):
            await QTAgent().process(_make_input(test_type="pytest", project_path="/my/project"))
        call_kwargs = mock_exec.call_args[1]
        assert call_kwargs.get("cwd") == "/my/project"

    async def test_pytest_output_in_result(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert "passed" in result["result"]["output"].lower()

    async def test_pytest_result_has_test_type_field(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["result"]["test_type"] == "pytest"


# ─────────────────────────────────────────────
# npm audit runner
# ─────────────────────────────────────────────

class TestQTAgentNpmAudit:
    async def test_returns_success_true_when_no_vulnerabilities(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_NPM_AUDIT_CLEAN)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="npm_audit"))
        assert result["success"] is True

    async def test_returns_success_false_when_high_vulnerabilities(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=1, stdout=_NPM_AUDIT_VULNS)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="npm_audit"))
        assert result["success"] is False

    async def test_vulnerabilities_dict_in_result(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=1, stdout=_NPM_AUDIT_VULNS)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="npm_audit"))
        vulns = result["result"]["vulnerabilities"]
        assert vulns["high"] == 1
        assert vulns["low"] == 2

    async def test_npm_audit_run_in_project_path(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_NPM_AUDIT_CLEAN)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc) as mock_exec, \
             patch("agents.qt.qt_agent.get_db_service"):
            await QTAgent().process(_make_input(test_type="npm_audit", project_path="/node/app"))
        call_kwargs = mock_exec.call_args[1]
        assert call_kwargs.get("cwd") == "/node/app"

    async def test_npm_audit_result_has_test_type_field(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_NPM_AUDIT_CLEAN)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="npm_audit"))
        assert result["result"]["test_type"] == "npm_audit"


# ─────────────────────────────────────────────
# Test generation
# ─────────────────────────────────────────────

class TestQTAgentGenerate:
    async def test_returns_success_true_when_generation_succeeds(self):
        from agents.qt.qt_agent import QTAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value={"response": "def test_foo(): assert foo() == 42"})
        with patch("agents.qt.qt_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(
                test_type="generate",
                code="def foo(): return 42",
            ))
        assert result["success"] is True

    async def test_generated_code_in_result(self):
        from agents.qt.qt_agent import QTAgent
        test_code = "def test_foo():\n    assert foo() == 42"
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value={"response": test_code})
        with patch("agents.qt.qt_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(
                test_type="generate",
                code="def foo(): return 42",
            ))
        assert result["result"]["generated"] == test_code

    async def test_result_type_is_generated(self):
        from agents.qt.qt_agent import QTAgent
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value={"response": "def test_x(): pass"})
        with patch("agents.qt.qt_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="generate", code="def x(): pass"))
        assert result["result"]["test_type"] == "generated"

    async def test_falls_back_to_claude_when_ollama_fails(self):
        from agents.qt.qt_agent import QTAgent

        mock_claude = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="def test_bar(): assert True")]
        mock_resp.usage = MagicMock(input_tokens=80, output_tokens=40)
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(return_value=mock_resp)

        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))

        with patch("agents.qt.qt_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.qt.qt_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="generate", code="def bar(): pass"))
        assert result["success"] is True
        assert result["result"]["generated"] is not None

    async def test_claude_fallback_tokens_tracked(self):
        from agents.qt.qt_agent import QTAgent

        mock_claude = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="def test_bar(): pass")]
        mock_resp.usage = MagicMock(input_tokens=80, output_tokens=40)
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(return_value=mock_resp)

        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))

        with patch("agents.qt.qt_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.qt.qt_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="generate", code="def bar(): pass"))
        assert result["tokens_used"] == 120  # 80 + 40


# ─────────────────────────────────────────────
# Approval gate
# ─────────────────────────────────────────────

class TestQTAgentApprovalGate:
    async def test_requires_approval_false_on_pytest_success(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["requires_approval"] is False

    async def test_requires_approval_false_on_pytest_failure(self):
        """Even when tests fail (blocking TITAN), no human approval needed — it's automatic."""
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=1, stdout=_PYTEST_FAIL_OUTPUT)
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Subprocess error handling
# ─────────────────────────────────────────────

class TestQTAgentErrorHandling:
    async def test_returns_error_when_subprocess_raises(self):
        from agents.qt.qt_agent import QTAgent
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, side_effect=FileNotFoundError("pytest not found")), \
             patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="pytest"))
        assert result["success"] is False
        assert result["error"] is not None

    async def test_returns_error_for_unknown_test_type(self):
        from agents.qt.qt_agent import QTAgent
        with patch("agents.qt.qt_agent.get_db_service"):
            result = await QTAgent().process(_make_input(test_type="playwright"))
        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestQTAgentLogging:
    async def test_log_called_with_success_on_passing_tests(self):
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=0, stdout=_PYTEST_PASS_OUTPUT)
        agent = QTAgent()
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input(test_type="pytest"))
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_with_success_on_failing_tests(self):
        """Failing tests is a valid (non-error) outcome — QT ran, found failures."""
        from agents.qt.qt_agent import QTAgent
        proc = _mock_process(returncode=1, stdout=_PYTEST_FAIL_OUTPUT)
        agent = QTAgent()
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.qt.qt_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input(test_type="pytest"))
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_with_error_on_subprocess_crash(self):
        from agents.qt.qt_agent import QTAgent
        agent = QTAgent()
        with patch("agents.qt.qt_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, side_effect=OSError("no such file")), \
             patch("agents.qt.qt_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input(test_type="pytest"))
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"


# ─────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────

class TestParsePytestOutput:
    def test_parses_all_passed(self):
        from agents.qt.qt_agent import _parse_pytest_output
        result = _parse_pytest_output(_PYTEST_PASS_OUTPUT.decode())
        assert result["passed"] == 2
        assert result["failed"] == 0
        assert result["errors"] == 0

    def test_parses_mixed_pass_fail(self):
        from agents.qt.qt_agent import _parse_pytest_output
        result = _parse_pytest_output(_PYTEST_FAIL_OUTPUT.decode())
        assert result["passed"] == 1
        assert result["failed"] == 1

    def test_parses_errors(self):
        from agents.qt.qt_agent import _parse_pytest_output
        result = _parse_pytest_output(_PYTEST_ERROR_OUTPUT.decode())
        assert result["errors"] == 1

    def test_returns_zeros_for_empty_output(self):
        from agents.qt.qt_agent import _parse_pytest_output
        result = _parse_pytest_output("")
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["errors"] == 0


class TestParseNpmAuditOutput:
    def test_parses_clean_audit(self):
        from agents.qt.qt_agent import _parse_npm_audit_output
        result = _parse_npm_audit_output(_NPM_AUDIT_CLEAN.decode())
        assert result["high"] == 0
        assert result["critical"] == 0

    def test_parses_audit_with_vulnerabilities(self):
        from agents.qt.qt_agent import _parse_npm_audit_output
        result = _parse_npm_audit_output(_NPM_AUDIT_VULNS.decode())
        assert result["low"] == 2
        assert result["high"] == 1

    def test_returns_empty_dict_on_invalid_json(self):
        from agents.qt.qt_agent import _parse_npm_audit_output
        result = _parse_npm_audit_output("not json")
        assert isinstance(result, dict)
