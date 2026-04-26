"""
QTAgent — test runner and quality gate.

Modes (via context["test_type"]):
  "pytest"    — run pytest in context["project_path"]
  "npm_audit" — run npm audit --json in context["project_path"]
  "generate"  — generate test code for context["code"] via Qwen 14B

Output (AgentOutput.result):
  {
    "test_type":       "pytest" | "npm_audit" | "generated",
    "passed":          <int>    (pytest only),
    "failed":          <int>    (pytest only),
    "errors":          <int>    (pytest only),
    "vulnerabilities": <dict>   (npm_audit only),
    "output":          "<raw runner output>",
    "generated":       "<test code>"  (generate mode only),
  }

AgentOutput.success:
  True  — all tests pass / no high+ vulns / test code generated
  False — tests failed / high/critical vulns found / subprocess crashed

AgentOutput.requires_approval:
  Always False — running tests and generating code are non-destructive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import anthropic

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.knowledge_base import get_kb_service
from services.ollama import OllamaService

logger = logging.getLogger("cruz.agents.QT")

_GENERATE_MODEL = "qwen2.5-coder:14b"

_GENERATE_SYSTEM = """\
You are QT, an expert test engineer in the CRUZ AI system.
Given a Python function or class, write comprehensive pytest tests.

Return ONLY the test code — no prose, no explanation, no markdown fences.
The code must be valid Python that can be saved directly to a .py file.

Guidelines:
- Import the subject under test at the top
- Cover: happy path, edge cases, error cases
- Use descriptive test names (test_<what>_<when>_<expected>)
- Use pytest.raises() for expected exceptions
- No external dependencies beyond pytest and the subject"""


class QTAgent(BaseAgent):
    """
    Test runner and pre-deploy quality gate.

    Dispatches to pytest, npm audit, or Qwen test generation
    based on context["test_type"]. Always returns requires_approval=False
    — running tests is non-destructive.
    """

    KNOWLEDGE_RINGS: list[str] = ["cruz_activities", "cruz_projects_docs"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "QT"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        test_type = input["context"].get("test_type", "pytest")
        output: Optional[AgentOutput] = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        # Most QT modes don't have an LLM call to inject context into;
        # the read still warms past-test telemetry, and the write below
        # records every QT run regardless of mode.
        kb = get_kb_service()
        await kb.build_agent_context(
            input["task"],
            self.KNOWLEDGE_RINGS,
            input["trace_id"],
            project_id=input["context"].get("project_id"),
        )

        try:
            try:
                if test_type == "pytest":
                    result, success = await self._run_pytest(input["context"])
                elif test_type == "npm_audit":
                    result, success = await self._run_npm_audit(input["context"])
                elif test_type == "playwright":
                    result, success = await self._run_playwright(input["context"])
                elif test_type == "lighthouse":
                    result, success = await self._run_lighthouse(input["context"])
                elif test_type == "generate":
                    result, success, tokens = await self._generate_tests(input)
                    duration = int((time.monotonic() - start) * 1000)
                    try:
                        await self.log(
                            db=db,
                            trace_id=input["trace_id"],
                            status="success",
                            input_data={"task": input["task"], "test_type": test_type},
                            output_data={"generated": bool(result.get("generated"))},
                            tokens_used=tokens,
                            duration_ms=duration,
                        )
                    except Exception:
                        pass
                    output = AgentOutput(
                        success=success,
                        result=result,
                        agent=self.name,
                        duration_ms=duration,
                        tokens_used=tokens,
                        error=None,
                        requires_approval=False,
                        approval_prompt=None,
                    )
                    return output
                else:
                    err = (
                        f"Unknown test_type '{test_type}'. "
                        f"Supported: pytest, npm_audit, playwright, lighthouse, generate."
                    )
                    try:
                        await self.log(
                            db=db,
                            trace_id=input["trace_id"],
                            status="error",
                            input_data={"task": input["task"], "test_type": test_type},
                            output_data={"error": err},
                            tokens_used=0,
                            duration_ms=int((time.monotonic() - start) * 1000),
                        )
                    except Exception:
                        pass
                    output = AgentOutput(
                        success=False,
                        result=None,
                        agent=self.name,
                        duration_ms=int((time.monotonic() - start) * 1000),
                        tokens_used=0,
                        error=err,
                        requires_approval=False,
                        approval_prompt=None,
                    )
                    return output

            except Exception as exc:
                err = str(exc)
                duration = int((time.monotonic() - start) * 1000)
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="error",
                        input_data={"task": input["task"], "test_type": test_type},
                        output_data={"error": err},
                        tokens_used=0,
                        duration_ms=duration,
                    )
                except Exception:
                    pass
                output = AgentOutput(
                    success=False,
                    result=None,
                    agent=self.name,
                    duration_ms=duration,
                    tokens_used=0,
                    error=err,
                    requires_approval=False,
                    approval_prompt=None,
                )
                return output

            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="success",
                    input_data={"task": input["task"], "test_type": test_type},
                    output_data=result,
                    tokens_used=0,
                    duration_ms=duration,
                )
            except Exception:
                pass

            output = AgentOutput(
                success=success,
                result=result,
                agent=self.name,
                duration_ms=duration,
                tokens_used=0,
                error=None,
                requires_approval=False,
                approval_prompt=None,
            )
            return output

        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "qt",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    # ── Runners ──────────────────────────────────────────────────────────────

    async def _run_pytest(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Run pytest and return (result_dict, success)."""
        project_path = context.get("project_path", ".")
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest", "--tb=short", "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=project_path,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace")
        parsed = _parse_pytest_output(output)
        success = proc.returncode == 0
        return {
            "test_type": "pytest",
            "passed": parsed["passed"],
            "failed": parsed["failed"],
            "errors": parsed["errors"],
            "output": output,
        }, success

    async def _run_npm_audit(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Run npm audit --json and return (result_dict, success)."""
        project_path = context.get("project_path", ".")
        proc = await asyncio.create_subprocess_exec(
            "npm", "audit", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=project_path,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace")
        vulns = _parse_npm_audit_output(output)
        # Block on high or critical vulnerabilities
        success = vulns.get("high", 0) == 0 and vulns.get("critical", 0) == 0
        return {
            "test_type": "npm_audit",
            "vulnerabilities": vulns,
            "output": output,
        }, success

    async def _run_playwright(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Run `npx playwright test` in project_path and parse pass/fail counts."""
        project_path = context.get("project_path", ".")
        proc = await asyncio.create_subprocess_exec(
            "npx", "playwright", "test",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=project_path,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace")
        parsed = _parse_playwright_output(output)
        success = proc.returncode == 0 and parsed["failed"] == 0
        return {
            "test_type": "playwright",
            "passed": parsed["passed"],
            "failed": parsed["failed"],
            "output": output,
        }, success

    async def _run_lighthouse(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """
        Run `npx lighthouse <url> --output=json` and gate on a score threshold.

        Default threshold is 0.9 (90%). Any category below threshold → success=False.
        Expects context["url"]; raises ValueError if missing.
        """
        url = (context.get("url") or "").strip()
        if not url:
            raise ValueError(
                "Lighthouse mode requires context['url'] — the target URL to audit."
            )
        threshold = float(context.get("threshold", 0.9))

        proc = await asyncio.create_subprocess_exec(
            "npx", "lighthouse", url,
            "--output=json", "--quiet", "--chrome-flags=--headless",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace")
        scores = _parse_lighthouse_output(output)
        # success = every category scored >= threshold
        success = (
            proc.returncode == 0
            and bool(scores)
            and all(s >= threshold for s in scores.values())
        )
        return {
            "test_type": "lighthouse",
            "url": url,
            "threshold": threshold,
            "scores": scores,
        }, success

    async def _generate_tests(
        self, input: AgentInput
    ) -> Tuple[Dict[str, Any], bool, int]:
        """Generate test code via Qwen (Ollama) with Claude Haiku fallback."""
        code = input["context"].get("code", input["task"])
        prompt = f"{_GENERATE_SYSTEM}\n\nCode to test:\n\n{code}"

        # Try Qwen via Ollama first
        try:
            ollama = OllamaService()
            response = await ollama.generate(model=_GENERATE_MODEL, prompt=prompt)
            generated = response.get("response", "")
            return {"test_type": "generated", "generated": generated, "output": ""}, True, 0
        except Exception as ollama_exc:
            logger.warning(
                "[%s] Ollama unavailable (%s) — falling back to Claude",
                input["trace_id"],
                ollama_exc,
            )

        # Claude Haiku fallback
        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        claude_resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        generated = claude_resp.content[0].text
        tokens = claude_resp.usage.input_tokens + claude_resp.usage.output_tokens
        return {"test_type": "generated", "generated": generated, "output": ""}, True, tokens


# ─────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────

def _parse_pytest_output(text: str) -> Dict[str, int]:
    """
    Extract pass/fail/error counts from pytest terminal output.

    Handles the standard summary line:
      "N passed, N failed, N error in Xs"
    Returns {"passed": 0, "failed": 0, "errors": 0} on no match.
    """
    result = {"passed": 0, "failed": 0, "errors": 0}
    if not text:
        return result

    # Match summary line: "1 passed", "2 failed", "1 error"
    passed_match = re.search(r"(\d+)\s+passed", text)
    failed_match = re.search(r"(\d+)\s+failed", text)
    error_match = re.search(r"(\d+)\s+error", text)

    if passed_match:
        result["passed"] = int(passed_match.group(1))
    if failed_match:
        result["failed"] = int(failed_match.group(1))
    if error_match:
        result["errors"] = int(error_match.group(1))

    return result


def _parse_npm_audit_output(text: str) -> Dict[str, int]:
    """
    Extract vulnerability counts from npm audit --json output.

    Returns {"low": 0, "moderate": 0, "high": 0, "critical": 0, ...}
    or an empty dict on parse failure.
    """
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text)
        vulns = data.get("metadata", {}).get("vulnerabilities", {})
        return {k: int(v) for k, v in vulns.items()}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _parse_playwright_output(text: str) -> Dict[str, int]:
    """
    Extract pass/fail counts from Playwright's default reporter output.

    Summary lines look like:
      "5 passed (12.3s)"
      "3 passed, 2 failed (14.1s)"
      "4 failed (2.0s)"
    """
    result = {"passed": 0, "failed": 0}
    passed = re.search(r"(\d+)\s+passed", text)
    failed = re.search(r"(\d+)\s+failed", text)
    if passed:
        result["passed"] = int(passed.group(1))
    if failed:
        result["failed"] = int(failed.group(1))
    return result


def _parse_lighthouse_output(text: str) -> Dict[str, float]:
    """
    Extract category scores from lighthouse --output=json output.

    Lighthouse prints the full JSON report to stdout. We pull out
    categories[k].score (float in [0, 1]) for the standard categories.

    Returns empty dict on parse failure.
    """
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    categories = data.get("categories") or {}
    scores: Dict[str, float] = {}
    for name, payload in categories.items():
        score = payload.get("score") if isinstance(payload, dict) else None
        if isinstance(score, (int, float)):
            scores[name] = float(score)
    return scores
