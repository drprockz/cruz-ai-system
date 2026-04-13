"""
Tests for TitanAgent — deployment agent with QT gate and approval gate.

Flow:
  1. Check QT gate — context["qt_passed"] must be True, else fail immediately
  2. Route to deploy target via context["target"]:
       "vercel"  → POST to Vercel Deployments API via httpx
       "railway" → POST to Railway GraphQL API via httpx
       "ssh"     → asyncio subprocess ssh command
  3. Return deployment result with requires_approval=True

Context dict:
  {
    "target":    "vercel" | "railway" | "ssh",
    "project":   "ama-website",
    "qt_passed": True,           # MUST be True or TITAN refuses

    # Vercel
    "vercel_project_id": "prj_xxx",

    # Railway
    "railway_service_id": "svc_xxx",
    "railway_environment_id": "env_xxx",

    # SSH
    "ssh_host":    "167.x.x.x",
    "ssh_user":    "ubuntu",
    "ssh_command": "cd /app && git pull && npm install && pm2 restart all",
  }

Output (AgentOutput.result):
  {
    "target":        "vercel" | "railway" | "ssh",
    "project":       "ama-website",
    "deployment_id": "<id or command hash>",
    "status":        "deploying" | "ready" | "success" | "error",
    "url":           "<deployment URL or empty string>",
  }

Rules:
  - requires_approval=True always — deployments are irreversible
  - QT gate failure → success=False, requires_approval=False
  - Unknown target → success=False
  - self.log() on success and error paths
  - Tokens tracked as 0 (Qwen local) — no cloud cost
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(
    task: str = "Deploy ama-website to production",
    target: str = "vercel",
    project: str = "ama-website",
    qt_passed: bool = True,
    extra_context: dict | None = None,
) -> AgentInput:
    ctx: dict = {
        "target": target,
        "project": project,
        "qt_passed": qt_passed,
        "vercel_project_id": "prj_test123",
        "railway_service_id": "svc_test456",
        "railway_environment_id": "env_test789",
        "ssh_host": "167.1.2.3",
        "ssh_user": "ubuntu",
        "ssh_command": "cd /app && git pull && pm2 restart all",
    }
    if extra_context:
        ctx.update(extra_context)
    return {
        "task": task,
        "context": ctx,
        "trace_id": "trace-titan-001",
        "conversation_id": "conv-titan-001",
    }


def _mock_process(returncode: int = 0, stdout: bytes = b"Deployed.", stderr: bytes = b""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def _setup_vercel_mock(mock_client_cls, deployment_id: str = "dpl_abc123"):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "id": deployment_id,
        "url": "ama-website.vercel.app",
        "readyState": "QUEUED",
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value = mock_client
    return mock_client


def _setup_railway_mock(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"serviceInstanceRedeploy": True}
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value = mock_client
    return mock_client


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestTitanAgentInterface:
    def test_titan_agent_can_be_imported(self):
        from agents.titan.titan_agent import TitanAgent  # noqa: F401

    def test_titan_agent_extends_base_agent(self):
        from agents.titan.titan_agent import TitanAgent
        assert issubclass(TitanAgent, BaseAgent)

    def test_titan_agent_name_is_TITAN(self):
        from agents.titan.titan_agent import TitanAgent
        assert TitanAgent().name == "TITAN"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.get_db_service"):
            coro = TitanAgent().process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()


# ─────────────────────────────────────────────
# QT gate
# ─────────────────────────────────────────────

class TestTitanQTGate:
    async def test_blocks_when_qt_passed_is_false(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(qt_passed=False))
        assert result["success"] is False

    async def test_qt_gate_error_mentions_qt(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(qt_passed=False))
        assert "qt" in result["error"].lower() or "test" in result["error"].lower()

    async def test_qt_gate_failure_does_not_require_approval(self):
        """Blocked by QT — nothing to approve."""
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(qt_passed=False))
        assert result["requires_approval"] is False

    async def test_blocks_when_qt_passed_missing_from_context(self):
        from agents.titan.titan_agent import TitanAgent
        inp = _make_input()
        del inp["context"]["qt_passed"]
        with patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(inp)
        assert result["success"] is False


# ─────────────────────────────────────────────
# Vercel deploy
# ─────────────────────────────────────────────

class TestTitanVercelDeploy:
    async def test_returns_success_on_vercel_deploy(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            result = await TitanAgent().process(_make_input(target="vercel"))
        assert result["success"] is True

    async def test_vercel_deployment_id_in_result(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc, deployment_id="dpl_xyz")
            result = await TitanAgent().process(_make_input(target="vercel"))
        assert result["result"]["deployment_id"] == "dpl_xyz"

    async def test_vercel_url_in_result(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            result = await TitanAgent().process(_make_input(target="vercel"))
        assert "vercel.app" in result["result"]["url"]

    async def test_vercel_api_called_with_project_id(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            mock_client = _setup_vercel_mock(mc)
            await TitanAgent().process(_make_input(
                target="vercel",
                extra_context={"vercel_project_id": "prj_myproject"},
            ))
        call_kwargs = mock_client.post.call_args
        body = str(call_kwargs)
        assert "prj_myproject" in body

    async def test_vercel_error_returns_failure(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Vercel API down"))
            mc.return_value = mock_client
            result = await TitanAgent().process(_make_input(target="vercel"))
        assert result["success"] is False


# ─────────────────────────────────────────────
# Railway deploy
# ─────────────────────────────────────────────

class TestTitanRailwayDeploy:
    async def test_returns_success_on_railway_deploy(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_railway_mock(mc)
            result = await TitanAgent().process(_make_input(target="railway"))
        assert result["success"] is True

    async def test_railway_target_in_result(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_railway_mock(mc)
            result = await TitanAgent().process(_make_input(target="railway"))
        assert result["result"]["target"] == "railway"

    async def test_railway_graphql_endpoint_called(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            mock_client = _setup_railway_mock(mc)
            await TitanAgent().process(_make_input(target="railway"))
        call_url = mock_client.post.call_args[0][0]
        assert "railway" in call_url.lower()

    async def test_railway_error_returns_failure(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Railway down"))
            mc.return_value = mock_client
            result = await TitanAgent().process(_make_input(target="railway"))
        assert result["success"] is False


# ─────────────────────────────────────────────
# SSH deploy
# ─────────────────────────────────────────────

class TestTitanSSHDeploy:
    async def test_returns_success_on_ssh_deploy(self):
        from agents.titan.titan_agent import TitanAgent
        proc = _mock_process(returncode=0, stdout=b"Deploy complete.")
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(target="ssh"))
        assert result["success"] is True

    async def test_ssh_failure_returns_false(self):
        from agents.titan.titan_agent import TitanAgent
        proc = _mock_process(returncode=1, stderr=b"Permission denied")
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(target="ssh"))
        assert result["success"] is False

    async def test_ssh_uses_host_and_user_from_context(self):
        from agents.titan.titan_agent import TitanAgent
        proc = _mock_process(returncode=0)
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc) as mock_exec, \
             patch("agents.titan.titan_agent.get_db_service"):
            await TitanAgent().process(_make_input(
                target="ssh",
                extra_context={"ssh_host": "10.0.0.5", "ssh_user": "deploy"},
            ))
        exec_args = mock_exec.call_args[0]
        full_cmd = " ".join(str(a) for a in exec_args)
        assert "deploy@10.0.0.5" in full_cmd

    async def test_ssh_command_executed_on_remote(self):
        from agents.titan.titan_agent import TitanAgent
        proc = _mock_process(returncode=0)
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc) as mock_exec, \
             patch("agents.titan.titan_agent.get_db_service"):
            await TitanAgent().process(_make_input(
                target="ssh",
                extra_context={"ssh_command": "cd /myapp && git pull"},
            ))
        exec_args = mock_exec.call_args[0]
        full_cmd = " ".join(str(a) for a in exec_args)
        assert "cd /myapp" in full_cmd

    async def test_ssh_output_in_result(self):
        from agents.titan.titan_agent import TitanAgent
        proc = _mock_process(returncode=0, stdout=b"Server restarted OK")
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   new_callable=AsyncMock, return_value=proc), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(target="ssh"))
        assert "Server restarted OK" in result["result"].get("output", "")


# ─────────────────────────────────────────────
# Approval gate
# ─────────────────────────────────────────────

class TestTitanApprovalGate:
    async def test_requires_approval_true_on_success(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            result = await TitanAgent().process(_make_input(target="vercel"))
        assert result["requires_approval"] is True

    async def test_approval_prompt_mentions_project_and_target(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            result = await TitanAgent().process(_make_input(
                target="vercel", project="shooterista"
            ))
        prompt = result["approval_prompt"].lower()
        assert "vercel" in prompt or "deploy" in prompt
        assert "shooterista" in prompt

    async def test_requires_approval_false_on_deploy_error(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("down"))
            mc.return_value = mock_client
            result = await TitanAgent().process(_make_input(target="vercel"))
        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Unknown target
# ─────────────────────────────────────────────

class TestTitanUnknownTarget:
    async def test_returns_error_for_unknown_target(self):
        from agents.titan.titan_agent import TitanAgent
        with patch("agents.titan.titan_agent.get_db_service"):
            result = await TitanAgent().process(_make_input(target="heroku"))
        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestTitanLogging:
    async def test_log_called_on_success(self):
        from agents.titan.titan_agent import TitanAgent
        agent = TitanAgent()
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input(target="vercel"))
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_on_qt_gate_failure(self):
        from agents.titan.titan_agent import TitanAgent
        agent = TitanAgent()
        with patch("agents.titan.titan_agent.get_db_service"):
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input(qt_passed=False))
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_called_on_deploy_failure(self):
        from agents.titan.titan_agent import TitanAgent
        agent = TitanAgent()
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Vercel down"))
            mc.return_value = mock_client
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input(target="vercel"))
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        from agents.titan.titan_agent import TitanAgent
        agent = TitanAgent()
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB dead")
                result = await agent.process(_make_input(target="vercel"))
        assert result["success"] is True
