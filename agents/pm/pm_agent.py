"""
PMAgent — sprint planning specialist.

Uses Qwen 2.5 Coder 14B via Ollama (local, zero cloud cost).
Falls back to Claude Haiku when Ollama is unavailable.

Flow:
  1. Build a structured prompt asking the model to generate a sprint plan as JSON
  2. Parse the JSON: {sprint_name, goal, tasks[{title, description, estimate_hours, priority, labels}]}
  3. Return AgentOutput with requires_approval=True — creating Linear tickets is irreversible
  4. User reviews and confirms before any Linear API calls are made (Phase 3 follow-up)

The Linear ticket creation is a separate step triggered only after user approval.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import anthropic

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.ollama import OllamaService
from typing_extensions import TypedDict

logger = logging.getLogger("cruz.agents.PM")

_MODEL = "qwen2.5-coder:14b"

_SYSTEM_PROMPT = """\
You are PM, an expert agile project manager embedded in the CRUZ AI system.

Given a project or feature description, create a structured 2-week sprint plan.
Respond ONLY with valid JSON — no prose, no markdown, no explanation.

JSON format:
{
  "sprint_name": "<Sprint N or descriptive name>",
  "goal": "<one-line sprint goal>",
  "tasks": [
    {
      "title": "<concise task title>",
      "description": "<what needs to be done and why>",
      "estimate_hours": <integer hours>,
      "priority": "high" | "medium" | "low",
      "labels": ["<relevant label>", ...]
    }
  ]
}

Guidelines:
- Break the work into 3-8 concrete tasks
- Estimate honestly — typical tasks are 2-8 hours
- Mark blockers or risky items as high priority
- Labels should be technology or domain categories (e.g. "frontend", "backend", "api", "testing")"""


class SprintTask(TypedDict):
    title: str
    description: str
    estimate_hours: int
    priority: str
    labels: List[str]


class SprintPlan(TypedDict):
    sprint_name: str
    goal: str
    tasks: List[SprintTask]


class PMAgent(BaseAgent):
    """
    Sprint planning agent backed by local Qwen 2.5 Coder 14B.

    Always returns requires_approval=True — the sprint plan is shown to
    the user before any Linear tickets are created.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "PM"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()

        try:
            plan, tokens_used = await self._plan_with_ollama(input["task"])
        except Exception as ollama_exc:
            logger.warning(
                "[%s] Ollama unavailable (%s) — falling back to Claude",
                input["trace_id"],
                ollama_exc,
            )
            try:
                plan, tokens_used = await self._plan_with_claude(input["task"])
            except Exception as claude_exc:
                output = self.handle_error(claude_exc, input["trace_id"])
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="error",
                        input_data={"task": input["task"]},
                        output_data={"error": str(claude_exc)},
                        tokens_used=0,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                except Exception:
                    pass
                return output

        if plan is None:
            err = "Could not parse a valid sprint plan from model response"
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"task": input["task"]},
                    output_data={"error": err},
                    tokens_used=tokens_used,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=tokens_used,
                error=err,
                requires_approval=False,
                approval_prompt=None,
            )

        task_count = len(plan["tasks"])
        approval_prompt = (
            f"Create {task_count} Linear ticket{'s' if task_count != 1 else ''} "
            f"for sprint '{plan['sprint_name']}'?\n"
            f"  Goal: {plan['goal']}\n"
            f"  Tasks: {task_count} items\n\n"
            f"Reply 'yes' to create in Linear or 'no' to discard."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"task": input["task"]},
                output_data={"plan": dict(plan)},
                tokens_used=tokens_used,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=plan,
            agent=self.name,
            duration_ms=duration,
            tokens_used=tokens_used,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    async def _plan_with_ollama(self, task: str):
        """Call Qwen via Ollama. Returns (plan, tokens_used) or raises."""
        ollama = OllamaService()
        prompt = f"{_SYSTEM_PROMPT}\n\nUser request: {task}"
        response = await ollama.generate(model=_MODEL, prompt=prompt)
        raw_text: str = response.get("response", "")
        return _parse_plan(raw_text), 0  # local — no cloud token cost

    async def _plan_with_claude(self, task: str):
        """Fallback: call Claude when Ollama is unavailable. Returns (plan, tokens_used)."""
        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",  # cheapest model for planning
            max_tokens=2048,
            messages=[{"role": "user", "content": f"{_SYSTEM_PROMPT}\n\nUser request: {task}"}],
        )
        raw_text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return _parse_plan(raw_text), tokens_used


# ─────────────────────────────────────────────
# Sprint plan parsing helpers
# ─────────────────────────────────────────────

def _parse_plan(text: str) -> Optional[SprintPlan]:
    """
    Extract sprint plan JSON from a model response.

    Handles three cases:
      1. Pure JSON string
      2. JSON wrapped in ```json ... ``` code fences
      3. JSON embedded anywhere in prose
    """
    if not text or not text.strip():
        return None

    # Strip code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    candidate = _try_parse(text.strip())
    if candidate:
        return candidate

    # Fall back: find the first {...} block in the text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = _try_parse(brace_match.group(0))
        if candidate:
            return candidate

    return None


def _try_parse(text: str) -> Optional[SprintPlan]:
    """Attempt to parse text as JSON and validate required fields."""
    try:
        data = json.loads(text)
        if all(k in data for k in ("sprint_name", "goal", "tasks")):
            return SprintPlan(
                sprint_name=str(data["sprint_name"]),
                goal=str(data["goal"]),
                tasks=[_coerce_task(t) for t in data["tasks"]],
            )
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None


def _coerce_task(raw: Dict[str, Any]) -> SprintTask:
    """Normalise a raw task dict — fill missing optional fields with defaults."""
    return SprintTask(
        title=str(raw.get("title", "")),
        description=str(raw.get("description", "")),
        estimate_hours=int(raw.get("estimate_hours", 0)),
        priority=str(raw.get("priority", "medium")),
        labels=[str(l) for l in raw.get("labels", [])],
    )
