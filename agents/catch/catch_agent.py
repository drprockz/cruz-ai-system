"""
CatchAgent — meeting transcription and summarisation specialist.

Flow:
  1. If context["audio_bytes"] is present: transcribe via Whisper (VoicePipeline)
     Otherwise: use task string directly as the transcript
  2. Validate transcript is non-empty (silent audio → failure)
  3. Summarise with Llama 3.1 8B via Ollama → structured meeting notes JSON
  4. Fall back to Claude Haiku if Ollama is unavailable
  5. Return AgentOutput with requires_approval=True
     (creating Notion pages and Linear tickets is irreversible)

Meeting notes structure:
  {
    "title":        "<meeting title>",
    "summary":      "<2-3 sentence summary>",
    "action_items": ["<owner>: <task>", ...],
    "decisions":    ["<decision made>", ...],
    "transcript":   "<full transcript text>"
  }
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
from services.voice import VoicePipeline
from typing_extensions import TypedDict

logger = logging.getLogger("cruz.agents.CATCH")

_SUMMARISE_MODEL = "llama3.1:8b"

_SYSTEM_PROMPT = """\
You are CATCH, an expert meeting intelligence assistant embedded in the CRUZ AI system.

Given a meeting transcript, extract structured notes.
Respond ONLY with valid JSON — no prose, no markdown, no explanation.

JSON format:
{
  "title": "<descriptive meeting title>",
  "summary": "<2-3 sentence summary of what was discussed and decided>",
  "action_items": [
    "<person name>: <specific task with deadline if mentioned>",
    ...
  ],
  "decisions": [
    "<clear statement of each decision made>",
    ...
  ]
}

Guidelines:
- Title should identify the meeting type and topic (e.g. "AMA Client Sync — April 14")
- Summary should be dense: what was discussed, what was resolved
- Action items must name the owner — if unclear, write "Team: <task>"
- Decisions are things agreed upon, not tasks
- Empty arrays are valid if there were no action items or decisions
- Keep action items and decisions concise and specific"""


class MeetingNotes(TypedDict):
    title: str
    summary: str
    action_items: List[str]
    decisions: List[str]
    transcript: str


class CatchAgent(BaseAgent):
    """
    Meeting transcription and summarisation agent.

    Uses Whisper Large v3 for STT and Llama 3.1 8B for summarisation.
    Always returns requires_approval=True — Notion and Linear writes are external.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "CATCH"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()

        # ── Step 1: Get transcript ────────────────────────────────────────
        audio_bytes: Optional[bytes] = input["context"].get("audio_bytes")

        if audio_bytes is not None:
            pipeline = VoicePipeline()
            transcript = await pipeline.transcribe(audio_bytes)
            if not transcript:
                err = "Audio transcript is empty — audio may be silent or unreadable"
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="error",
                        input_data={"task": input["task"]},
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
        else:
            transcript = input["task"]

        # ── Step 2: Summarise ─────────────────────────────────────────────
        try:
            notes, tokens_used = await self._summarise_with_ollama(transcript)
        except Exception as ollama_exc:
            logger.warning(
                "[%s] Ollama unavailable (%s) — falling back to Claude",
                input["trace_id"],
                ollama_exc,
            )
            try:
                notes, tokens_used = await self._summarise_with_claude(transcript)
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

        if notes is None:
            err = "Could not parse structured meeting notes from model response"
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

        # ── Step 3: Attach transcript and build output ────────────────────
        full_result: MeetingNotes = {
            **notes,
            "transcript": transcript,
        }

        action_count = len(notes["action_items"])
        approval_prompt = (
            f"Save meeting notes to Notion and create {action_count} "
            f"Linear ticket{'s' if action_count != 1 else ''}?\n"
            f"  Title: {notes['title']}\n"
            f"  Action items: {action_count}\n\n"
            f"Reply 'yes' to save or 'no' to discard."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"task": input["task"]},
                output_data={"notes": dict(notes)},
                tokens_used=tokens_used,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=full_result,
            agent=self.name,
            duration_ms=duration,
            tokens_used=tokens_used,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    async def _summarise_with_ollama(self, transcript: str):
        """Call Llama 3.1 8B via Ollama. Returns (notes, tokens_used) or raises."""
        ollama = OllamaService()
        prompt = f"{_SYSTEM_PROMPT}\n\nTranscript:\n{transcript}"
        response = await ollama.generate(model=_SUMMARISE_MODEL, prompt=prompt)
        raw_text: str = response.get("response", "")
        return _parse_notes(raw_text), 0  # local — no cloud token cost

    async def _summarise_with_claude(self, transcript: str):
        """Fallback: call Claude when Ollama is unavailable. Returns (notes, tokens_used)."""
        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"{_SYSTEM_PROMPT}\n\nTranscript:\n{transcript}",
            }],
        )
        raw_text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return _parse_notes(raw_text), tokens_used


# ─────────────────────────────────────────────
# Meeting notes parsing helpers
# ─────────────────────────────────────────────

def _parse_notes(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract meeting notes JSON from a model response.

    Handles: pure JSON, ```json fenced, JSON embedded in prose.
    Required fields: title, summary, action_items.
    """
    if not text or not text.strip():
        return None

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    candidate = _try_parse(text.strip())
    if candidate:
        return candidate

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = _try_parse(brace_match.group(0))
        if candidate:
            return candidate

    return None


def _try_parse(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON and validate required fields."""
    try:
        data = json.loads(text)
        if all(k in data for k in ("title", "summary", "action_items")):
            return {
                "title": str(data["title"]),
                "summary": str(data["summary"]),
                "action_items": [str(i) for i in data.get("action_items", [])],
                "decisions": [str(d) for d in data.get("decisions", [])],
            }
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None
