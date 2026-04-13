"""
EchoAgent — email and message drafting specialist.

Uses Qwen 2.5 Coder 14B via Ollama (local, zero cloud cost).
ALWAYS requires human approval before anything is sent — no exceptions.

Flow:
  1. Build a structured prompt asking Ollama to draft the email as JSON
  2. Parse the JSON response: {to, subject, body}
  3. Return AgentOutput with requires_approval=True and a clear approval_prompt

The Gmail send action (Phase 3) is a separate step that only runs
after the user confirms via the approval gate.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

import anthropic

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.ollama import OllamaService
from typing_extensions import TypedDict

logger = logging.getLogger("cruz.agents.ECHO")

_MODEL = "qwen2.5-coder:14b"

_SYSTEM_PROMPT = """\
You are ECHO, an expert communication assistant.
Draft a professional email based on the user's request.
Respond ONLY with valid JSON — no prose, no markdown, no explanation.

JSON format:
{
  "to": "<recipient email or name if unknown>",
  "subject": "<concise subject line>",
  "body": "<full email body, professional tone>"
}"""


class EmailDraft(TypedDict):
    to: str
    subject: str
    body: str


class EchoAgent(BaseAgent):
    """
    Email drafting agent backed by local Qwen 2.5 Coder 14B.

    Always returns requires_approval=True — the draft is shown to the
    user for review before any send action is triggered.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "ECHO"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()

        try:
            draft, tokens_used = await self._draft_with_ollama(input["task"])
        except (ConnectionError, OSError, Exception) as ollama_exc:
            logger.warning(
                "[%s] Ollama unavailable (%s) — falling back to Claude",
                input["trace_id"],
                ollama_exc,
            )
            try:
                draft, tokens_used = await self._draft_with_claude(input["task"])
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

        if draft is None:
            err = "Could not parse a valid email draft from model response"
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

        approval_prompt = (
            f"Send this email?\n"
            f"  To: {draft['to']}\n"
            f"  Subject: {draft['subject']}\n\n"
            f"Reply 'yes' to send or 'no' to discard."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"task": input["task"]},
                output_data={"draft": dict(draft)},
                tokens_used=tokens_used,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=draft,
            agent=self.name,
            duration_ms=duration,
            tokens_used=tokens_used,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    async def _draft_with_ollama(self, task: str):
        """Call Qwen via Ollama. Returns (draft, tokens_used) or raises."""
        ollama = OllamaService()
        prompt = f"{_SYSTEM_PROMPT}\n\nUser request: {task}"
        response = await ollama.generate(model=_MODEL, prompt=prompt)
        raw_text: str = response.get("response", "")
        return _parse_draft(raw_text), 0  # local — no cloud token cost

    async def _draft_with_claude(self, task: str):
        """Fallback: call Claude when Ollama is unavailable. Returns (draft, tokens_used)."""
        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",  # cheapest model for drafting
            max_tokens=1024,
            messages=[{"role": "user", "content": f"{_SYSTEM_PROMPT}\n\nUser request: {task}"}],
        )
        raw_text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return _parse_draft(raw_text), tokens_used


# ─────────────────────────────────────────────
# Draft parsing helpers
# ─────────────────────────────────────────────

def _parse_draft(text: str) -> Optional[EmailDraft]:
    """
    Extract {to, subject, body} JSON from Ollama's response.

    Handles three cases:
      1. Pure JSON string
      2. JSON wrapped in ```json ... ``` code fences
      3. JSON embedded anywhere in prose
    """
    # Strip code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    # Try parsing the whole string first
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


def _try_parse(text: str) -> Optional[EmailDraft]:
    """Attempt to parse text as JSON and validate required fields."""
    try:
        data = json.loads(text)
        if all(k in data for k in ("to", "subject", "body")):
            return EmailDraft(
                to=str(data["to"]),
                subject=str(data["subject"]),
                body=str(data["body"]),
            )
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None
