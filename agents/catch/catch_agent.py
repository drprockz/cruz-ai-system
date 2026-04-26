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
from services.knowledge_base import get_kb_service
from services.ollama import OllamaService
from services.plane import PlaneService
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

    KNOWLEDGE_RINGS: list[str] = [
        "cruz_activities",
        "cruz_projects_docs",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.name = "CATCH"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        output: Optional[AgentOutput] = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        kb_context = await kb.build_agent_context(
            input["task"],
            self.KNOWLEDGE_RINGS,
            input["trace_id"],
            project_id=input["context"].get("project_id"),
        )
        system = _SYSTEM_PROMPT
        if kb_context:
            system = kb_context + "\n\n" + system

        try:
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
            else:
                transcript = input["task"]

            # ── Step 2: Summarise ─────────────────────────────────────────────
            try:
                notes, tokens_used = await self._summarise_with_ollama(transcript, system)
            except Exception as ollama_exc:
                logger.warning(
                    "[%s] Ollama unavailable (%s) — falling back to Claude",
                    input["trace_id"],
                    ollama_exc,
                )
                try:
                    notes, tokens_used = await self._summarise_with_claude(transcript, system)
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
                output = AgentOutput(
                    success=False,
                    result=None,
                    agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=tokens_used,
                    error=err,
                    requires_approval=False,
                    approval_prompt=None,
                )
                return output

            # ── Step 3: Attach transcript and build output ────────────────────
            full_result: Dict[str, Any] = {
                **notes,
                "transcript": transcript,
            }

            action_count = len(notes["action_items"])

            # ── Send mode: context["send"]=True → Plane issue per action item
            ctx = input["context"]
            if ctx.get("send") is True:
                workspace_slug = ctx.get("workspace_slug", "")
                project_id = ctx.get("project_id", "")
                plane_svc = PlaneService()
                created_count = 0
                failed_count = 0
                enriched: List[Dict[str, Any]] = []

                for item in notes["action_items"]:
                    row: Dict[str, Any] = {"action_item": item}
                    try:
                        issue = await plane_svc.create_issue(
                            workspace_slug=workspace_slug,
                            project_id=project_id,
                            title=item,
                            description=(
                                f"From meeting: **{notes['title']}**\n\n"
                                f"{notes.get('summary', '')}"
                            ),
                        )
                        row["created"] = True
                        row["issue_id"] = issue.get("issue_id", "")
                        row["issue_url"] = issue.get("url", "")
                        created_count += 1
                    except Exception as exc:
                        row["created"] = False
                        row["create_error"] = str(exc)
                        failed_count += 1
                        logger.warning(
                            "[%s] CATCH Plane create failed for '%s': %s",
                            input["trace_id"], item, exc,
                        )
                    enriched.append(row)

                send_result = {
                    **full_result,
                    "action_items_with_status": enriched,
                    "created_count": created_count,
                    "failed_count": failed_count,
                }

                duration = int((time.monotonic() - start) * 1000)
                any_success = created_count > 0 or action_count == 0
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="success" if any_success else "error",
                        input_data={
                            "task": input["task"],
                            "mode": "send",
                            "workspace_slug": workspace_slug,
                            "project_id": project_id,
                        },
                        output_data={
                            "created_count": created_count,
                            "failed_count": failed_count,
                        },
                        tokens_used=tokens_used,
                        duration_ms=duration,
                    )
                except Exception:
                    pass

                output = AgentOutput(
                    success=any_success,
                    result=send_result,
                    agent=self.name,
                    duration_ms=duration,
                    tokens_used=tokens_used,
                    error=None if any_success else "All Plane create_issue calls failed",
                    requires_approval=False,
                    approval_prompt=None,
                )
                return output

            # ── Draft-only (default): approval gate ──────────────────────────
            approval_prompt = (
                f"Save meeting notes to Notion and create {action_count} "
                f"Plane issue{'s' if action_count != 1 else ''}?\n"
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

            output = AgentOutput(
                success=True,
                result=full_result,
                agent=self.name,
                duration_ms=duration,
                tokens_used=tokens_used,
                error=None,
                requires_approval=True,
                approval_prompt=approval_prompt,
            )
            return output

        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "catch",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    async def _summarise_with_ollama(self, transcript: str, system: str = _SYSTEM_PROMPT):
        """Call Llama 3.1 8B via Ollama. Returns (notes, tokens_used) or raises."""
        ollama = OllamaService()
        prompt = f"{system}\n\nTranscript:\n{transcript}"
        response = await ollama.generate(model=_SUMMARISE_MODEL, prompt=prompt)
        raw_text: str = response.get("response", "")
        return _parse_notes(raw_text), 0  # local — no cloud token cost

    async def _summarise_with_claude(self, transcript: str, system: str = _SYSTEM_PROMPT):
        """Fallback: call Claude when Ollama is unavailable. Returns (notes, tokens_used)."""
        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"{system}\n\nTranscript:\n{transcript}",
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
