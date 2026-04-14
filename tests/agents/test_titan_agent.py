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


# ─────────────────────────────────────────────
# R14 — Auto-rollback on failed deploy
# ─────────────────────────────────────────────

from agents.titan.titan_agent import TitanAgent  # noqa: E402


def _vercel_failing_client(rollback_ok: bool = True):
    """AsyncClient whose first POST raises, second (rollback) succeeds iff rollback_ok."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    deploy_exc = Exception("Vercel API 500")
    ok_resp = MagicMock()
    ok_resp.json.return_value = {"id": "dpl_rollback"}
    ok_resp.raise_for_status = MagicMock()
    if rollback_ok:
        client.post = AsyncMock(side_effect=[deploy_exc, ok_resp])
    else:
        client.post = AsyncMock(side_effect=[deploy_exc, Exception("Rollback 500")])
    return client


@pytest.mark.asyncio
class TestTitanAutoRollback:
    async def test_vercel_deploy_failure_triggers_rollback_when_prev_id_given(self):
        """Failed deploy + previous_deployment_id + auto_rollback default → rollback attempted."""
        agent = TitanAgent()
        client = _vercel_failing_client(rollback_ok=True)
        with patch("agents.titan.titan_agent.httpx.AsyncClient", return_value=client), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(
                target="vercel",
                extra_context={"previous_deployment_id": "dpl_prev_good"},
            ))
        # The POST was called twice: the failed deploy + the rollback
        assert client.post.call_count == 2
        # Second call was a promote/rollback URL with the previous id
        second_url = client.post.call_args_list[1][0][0]
        assert "dpl_prev_good" in second_url
        assert result["result"]["rolled_back"] is True
        assert result["success"] is False  # deploy failed — success reflects deploy, not rollback

    async def test_vercel_deploy_failure_skips_rollback_without_prev_id(self):
        """No previous_deployment_id → rollback skipped with reason, no extra POST."""
        agent = TitanAgent()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(side_effect=Exception("Vercel API 500"))
        with patch("agents.titan.titan_agent.httpx.AsyncClient", return_value=client), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(target="vercel"))
        # Only the failed deploy POST — no rollback call
        assert client.post.call_count == 1
        assert result["result"]["rolled_back"] is False
        assert "previous_deployment_id" in (result["result"].get("rollback_skipped_reason") or "")

    async def test_vercel_deploy_failure_rollback_failure_reported(self):
        agent = TitanAgent()
        client = _vercel_failing_client(rollback_ok=False)
        with patch("agents.titan.titan_agent.httpx.AsyncClient", return_value=client), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(
                target="vercel",
                extra_context={"previous_deployment_id": "dpl_prev"},
            ))
        assert result["result"]["rolled_back"] is False
        assert "Rollback" in (result["result"].get("rollback_error") or "")

    async def test_auto_rollback_false_skips_rollback_even_on_failure(self):
        agent = TitanAgent()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(side_effect=Exception("Vercel API 500"))
        with patch("agents.titan.titan_agent.httpx.AsyncClient", return_value=client), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(
                target="vercel",
                extra_context={
                    "previous_deployment_id": "dpl_prev",
                    "auto_rollback": False,
                },
            ))
        assert client.post.call_count == 1  # no rollback attempted
        assert result["result"]["rolled_back"] is False
        assert "disabled" in (result["result"].get("rollback_skipped_reason") or "").lower()

    async def test_successful_deploy_does_not_attempt_rollback(self):
        """Happy path — no rollback logic runs. Result has rolled_back=False as a marker."""
        agent = TitanAgent()
        with patch("agents.titan.titan_agent.httpx.AsyncClient") as mc, \
             patch("agents.titan.titan_agent.get_db_service"):
            _setup_vercel_mock(mc)
            result = await agent.process(_make_input(target="vercel"))
        # Successful deploy keeps existing behavior
        assert result["success"] is True
        assert result["result"]["rolled_back"] is False
        assert result["requires_approval"] is True

    async def test_ssh_deploy_failure_runs_rollback_command(self):
        agent = TitanAgent()
        # First subprocess = failed deploy, second = successful rollback
        failed_proc = _mock_process(returncode=1, stdout=b"", stderr=b"oops")
        rollback_proc = _mock_process(returncode=0, stdout=b"rolled back", stderr=b"")
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   AsyncMock(side_effect=[failed_proc, rollback_proc])) as mock_exec, \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(
                target="ssh",
                extra_context={"ssh_rollback_command": "cd /app && git revert --no-edit HEAD"},
            ))
        assert mock_exec.call_count == 2
        assert result["result"]["rolled_back"] is True
        assert result["success"] is False  # deploy failed

    async def test_ssh_deploy_failure_skips_rollback_without_command(self):
        agent = TitanAgent()
        failed_proc = _mock_process(returncode=1, stdout=b"", stderr=b"oops")
        with patch("agents.titan.titan_agent.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=failed_proc)) as mock_exec, \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(target="ssh"))  # no rollback_command
        # Only the failed deploy subprocess
        assert mock_exec.call_count == 1
        assert result["result"]["rolled_back"] is False
        assert "ssh_rollback_command" in (result["result"].get("rollback_skipped_reason") or "")

    async def test_railway_deploy_failure_redeploys_previous(self):
        """Railway rollback re-runs serviceInstanceRedeploy with rollback_service_id."""
        agent = TitanAgent()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        fail_resp = MagicMock()
        fail_resp.json.return_value = {"data": {"serviceInstanceRedeploy": False}}
        fail_resp.raise_for_status = MagicMock()

        ok_resp = MagicMock()
        ok_resp.json.return_value = {"data": {"serviceInstanceRedeploy": True}}
        ok_resp.raise_for_status = MagicMock()

        client.post = AsyncMock(side_effect=[fail_resp, ok_resp])

        with patch("agents.titan.titan_agent.httpx.AsyncClient", return_value=client), \
             patch("agents.titan.titan_agent.get_db_service"):
            result = await agent.process(_make_input(
                target="railway",
                extra_context={
                    "rollback_service_id": "svc_prev",
                    "rollback_environment_id": "env_prev",
                },
            ))
        assert client.post.call_count == 2
        # Second payload uses the rollback service + environment ids
        second_body = str(client.post.call_args_list[1])
        assert "svc_prev" in second_body
        assert result["result"]["rolled_back"] is True
