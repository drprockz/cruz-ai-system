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
import re
import time
from typing import Optional

import anthropic  # imported so tests can assert it is NOT called

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
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

        try:
            ollama = OllamaService()

            prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                f"User request: {input['task']}"
            )

            response = await ollama.generate(
                model=_MODEL,
                prompt=prompt,
            )

            raw_text: str = response.get("response", "")
            draft = _parse_draft(raw_text)

            if draft is None:
                return AgentOutput(
                    success=False,
                    result=None,
                    agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=0,
                    error=f"Could not parse a valid email draft from model response: {raw_text[:200]}",
                    requires_approval=False,
                    approval_prompt=None,
                )

            approval_prompt = (
                f"Send this email?\n"
                f"  To: {draft['to']}\n"
                f"  Subject: {draft['subject']}\n\n"
                f"Reply 'yes' to send or 'no' to discard."
            )

            return AgentOutput(
                success=True,
                result=draft,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=0,  # Ollama is local — no cloud token cost
                error=None,
                requires_approval=True,
                approval_prompt=approval_prompt,
            )

        except Exception as exc:
            return self.handle_error(exc, input["trace_id"])


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
