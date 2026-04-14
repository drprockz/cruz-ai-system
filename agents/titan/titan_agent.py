"""
TitanAgent — deployment agent with QT gate and approval gate.

Flow:
  1. QT gate: context["qt_passed"] must be True — refuse immediately if not
  2. Route to deploy target via context["target"]:
       "vercel"  → POST to Vercel Deployments API (httpx)
       "railway" → POST to Railway GraphQL API (httpx)
       "ssh"     → asyncio subprocess ssh command
  3. Return deployment result with requires_approval=True

requires_approval is True on any successful deploy result — the operator
must confirm before the result is forwarded to clients or auto-published.
On QT gate failure or deploy error it is False (nothing to approve).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service

logger = logging.getLogger("cruz.agents.TITAN")

_VERCEL_API = "https://api.vercel.com"
_RAILWAY_API = "https://backboard.railway.app/graphql/v2"


class TitanAgent(BaseAgent):
    """
    Deployment agent.

    Checks the QT gate, then dispatches to Vercel, Railway, or SSH.
    Always returns requires_approval=True on a successful deploy — the
    operator confirms before the deployment is treated as authorised.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "TITAN"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        target = input["context"].get("target", "")
        project = input["context"].get("project", "")

        # ── QT gate ──────────────────────────────────────────────────────
        if not input["context"].get("qt_passed", False):
            err = "QT gate not passed — all tests must pass before deploying."
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"target": target, "project": project},
                    output_data={"error": err},
                    tokens_used=0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=err,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Unknown target — refuse immediately, no rollback ─────────────
        if target not in ("vercel", "railway", "ssh"):
            err = f"Unknown deploy target '{target}'. Supported: vercel, railway, ssh."
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"target": target, "project": project},
                    output_data={"error": err},
                    tokens_used=0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,
                error=err,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Dispatch to target ────────────────────────────────────────────
        deploy_result: Dict[str, Any] = {}
        deploy_ok = False
        deploy_error: Optional[str] = None
        try:
            if target == "vercel":
                deploy_result, deploy_ok = await self._deploy_vercel(input["context"])
            elif target == "railway":
                deploy_result, deploy_ok = await self._deploy_railway(input["context"])
            else:  # ssh
                deploy_result, deploy_ok = await self._deploy_ssh(input["context"])
        except Exception as exc:
            deploy_error = str(exc)
            deploy_result = {
                "target": target,
                "project": project,
                "error": deploy_error,
            }

        # ── Deploy failed → attempt rollback ──────────────────────────────
        if not deploy_ok:
            auto_rollback = input["context"].get("auto_rollback", True)
            if not auto_rollback:
                deploy_result["rolled_back"] = False
                deploy_result["rollback_skipped_reason"] = "auto_rollback disabled"
            else:
                rb = await self._rollback(target, input["context"])
                deploy_result.update(rb)

            err_msg = deploy_error or "Deploy reported failure"
            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"target": target, "project": project},
                    output_data={
                        "error": err_msg,
                        "rolled_back": deploy_result.get("rolled_back", False),
                    },
                    tokens_used=0,
                    duration_ms=duration,
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=deploy_result,
                agent=self.name,
                duration_ms=duration,
                tokens_used=0,
                error=err_msg,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Deploy succeeded → approval gate (existing behavior) ─────────
        deploy_result["rolled_back"] = False
        approval_prompt = (
            f"Deploy {project} to {target}?\n"
            f"  Deployment ID: {deploy_result.get('deployment_id', 'N/A')}\n"
            f"  URL: {deploy_result.get('url', 'N/A')}\n"
            f"  QT: passed ✓\n\n"
            f"Reply 'yes' to confirm or 'no' to rollback."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"target": target, "project": project},
                output_data=deploy_result,
                tokens_used=0,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=deploy_result,
            agent=self.name,
            duration_ms=duration,
            tokens_used=0,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    # ── Deploy targets ────────────────────────────────────────────────────

    async def _deploy_vercel(
        self, context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool]:
        """Trigger a Vercel deployment via the Deployments API."""
        token = os.environ.get("VERCEL_TOKEN", "")
        project_id = context.get("vercel_project_id", "")
        project = context.get("project", "")

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}
        ) as client:
            resp = await client.post(
                f"{_VERCEL_API}/v13/deployments",
                json={"name": project, "project": project_id, "target": "production"},
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "target": "vercel",
            "project": project,
            "deployment_id": data.get("id", ""),
            "status": data.get("readyState", "deploying").lower(),
            "url": data.get("url", ""),
        }, True

    async def _deploy_railway(
        self, context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool]:
        """Trigger a Railway redeploy via the GraphQL API."""
        token = os.environ.get("RAILWAY_TOKEN", "")
        service_id = context.get("railway_service_id", "")
        environment_id = context.get("railway_environment_id", "")
        project = context.get("project", "")

        mutation = """
        mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
          serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}
        ) as client:
            resp = await client.post(
                _RAILWAY_API,
                json={
                    "query": mutation,
                    "variables": {
                        "serviceId": service_id,
                        "environmentId": environment_id,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        success = bool(
            data.get("data", {}).get("serviceInstanceRedeploy", False)
        )
        return {
            "target": "railway",
            "project": project,
            "deployment_id": f"railway-{service_id}",
            "status": "deploying" if success else "error",
            "url": "",
        }, success

    async def _deploy_ssh(
        self, context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool]:
        """Run a deploy command on a remote host via SSH subprocess."""
        host = context.get("ssh_host", "")
        user = context.get("ssh_user", "ubuntu")
        command = context.get("ssh_command", "")
        project = context.get("project", "")

        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            f"{user}@{host}",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode(errors="replace")
        success = proc.returncode == 0

        return {
            "target": "ssh",
            "project": project,
            "deployment_id": f"ssh-{host}",
            "status": "success" if success else "error",
            "url": "",
            "output": output,
        }, success

    # ── Rollback helpers (R14) ────────────────────────────────────────────

    async def _rollback(
        self, target: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Dispatch to the target-specific rollback path.

        Returns a dict with:
          rolled_back: bool
          rollback_error: str (only on rollback exception)
          rollback_skipped_reason: str (only when skipped intentionally)
        """
        try:
            if target == "vercel":
                return await self._rollback_vercel(context)
            if target == "railway":
                return await self._rollback_railway(context)
            if target == "ssh":
                return await self._rollback_ssh(context)
        except Exception as exc:
            return {"rolled_back": False, "rollback_error": str(exc)}
        return {"rolled_back": False, "rollback_skipped_reason": "unsupported target"}

    async def _rollback_vercel(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Promote a previously successful deployment back to production."""
        prev_id = (context.get("previous_deployment_id") or "").strip()
        if not prev_id:
            return {
                "rolled_back": False,
                "rollback_skipped_reason": (
                    "no previous_deployment_id in context — cannot rollback"
                ),
            }
        token = os.environ.get("VERCEL_TOKEN", "")
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}
        ) as client:
            resp = await client.post(
                f"{_VERCEL_API}/v13/deployments/{prev_id}/promote",
            )
            resp.raise_for_status()
        return {"rolled_back": True}

    async def _rollback_railway(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Re-run serviceInstanceRedeploy against a prior service + env pair."""
        prev_service = (context.get("rollback_service_id") or "").strip()
        prev_env = (context.get("rollback_environment_id") or "").strip()
        if not prev_service or not prev_env:
            return {
                "rolled_back": False,
                "rollback_skipped_reason": (
                    "no rollback_service_id / rollback_environment_id in context"
                ),
            }
        token = os.environ.get("RAILWAY_TOKEN", "")
        mutation = """
        mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
          serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}
        ) as client:
            resp = await client.post(
                _RAILWAY_API,
                json={
                    "query": mutation,
                    "variables": {
                        "serviceId": prev_service,
                        "environmentId": prev_env,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
        ok = bool((data.get("data") or {}).get("serviceInstanceRedeploy", False))
        if not ok:
            return {
                "rolled_back": False,
                "rollback_error": "Railway serviceInstanceRedeploy returned false",
            }
        return {"rolled_back": True}

    async def _rollback_ssh(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run a caller-supplied rollback command over SSH."""
        command = (context.get("ssh_rollback_command") or "").strip()
        if not command:
            return {
                "rolled_back": False,
                "rollback_skipped_reason": (
                    "no ssh_rollback_command in context — cannot rollback"
                ),
            }
        host = context.get("ssh_host", "")
        user = context.get("ssh_user", "ubuntu")
        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            f"{user}@{host}",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {
                "rolled_back": False,
                "rollback_error": (
                    f"SSH rollback exit={proc.returncode}: "
                    f"{stderr.decode(errors='replace')[:200]}"
                ),
            }
        return {"rolled_back": True}
