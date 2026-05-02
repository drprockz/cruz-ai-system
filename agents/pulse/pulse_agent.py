"""
PulseAgent — 6 AM daily morning briefing.

Assembles a structured briefing from four data sources:
  1. Google Calendar API  — today's events (gracefully skipped if no token)
  2. Qdrant semantic memory — RAW's overnight research findings
  3. agent_logs            — what agents ran overnight (last 8 hours)
  4. tasks table           — pending/in-progress tasks

Feeds all context to Llama 3.1 8B to generate a natural morning brief.

Primary model: Llama 3.1 8B via Ollama (local, zero cost)
Fallback: Claude Haiku when Ollama unavailable

Output (AgentOutput.result):
  {
    "date":               "<YYYY-MM-DD>",
    "calendar_events":    [{title, start, end}, ...],
    "overnight_research": "<RAW findings summary from Qdrant>",
    "overnight_agents":   [{agent, status, last_run}, ...],
    "pending_tasks":      [{title, agent, priority}, ...],
    "summary":            "<Llama-generated morning briefing>",
  }

requires_approval=False — read-only briefing, no external actions.
All data-source failures are non-fatal — degrade gracefully.
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import anthropic
import httpx
import yaml

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.embedding import get_embedding_service
from services.knowledge_base import get_kb_service
from services.ollama import OllamaService
from services.qdrant import get_qdrant_service
from services.semantic_memory import SemanticMemoryService

logger = logging.getLogger("cruz.agents.PULSE")

_MODEL = "llama3.1:8b"

_GOOGLE_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

_SOURCES_PATH = str(Path(__file__).parent / "sources.yml")


def _load_pages() -> list[dict]:
    """Load page entries from sources.yml. Returns [] if file missing/empty."""
    try:
        with open(_SOURCES_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("pages") or []
    except FileNotFoundError:
        return []


_SYSTEM_PROMPT = """You are PULSE, Darshan's morning briefing assistant.
Given today's calendar, overnight research, agent activity, and pending tasks,
write a concise, actionable morning briefing in a professional but friendly tone.
Structure it as: greeting, today's calendar highlights, overnight work summary,
research highlights, top priorities. Keep it under 300 words."""


class PulseAgent(BaseAgent):
    """
    Morning briefing agent.

    Runs at 6 AM via ARQ cron. Assembles context from Calendar,
    Qdrant, agent_logs, and tasks table, then generates a natural
    language briefing via Llama 3.1 8B.
    requires_approval=False — read-only.
    """

    KNOWLEDGE_RINGS: list[str] = ["cruz_activities", "cruz_domain_knowledge"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "PULSE"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        today = datetime.date.today().isoformat()
        output: AgentOutput | None = None

        # ── KB context (fire-and-forget; never raises) ───────────────────
        kb = get_kb_service()
        kb_context = await kb.build_agent_context(
            input["task"],
            self.KNOWLEDGE_RINGS,
            input["trace_id"],
            project_id=input["context"].get("project_id"),
        )

        try:
            # ── Gather all data sources (all non-fatal) ───────────────────
            calendar_events = await self._gather_calendar()
            overnight_research = await self._gather_research()
            overnight_agents = await self._gather_overnight_agents(db)
            pending_tasks = await self._gather_pending_tasks(db)
            # Browser-sourced roundup (new in SP4)
            web_roundup = await self._gather_web_roundup(input["trace_id"])

            # ── Build briefing prompt ─────────────────────────────────────
            prompt = _build_prompt(
                today=today,
                calendar_events=calendar_events,
                overnight_research=overnight_research,
                overnight_agents=overnight_agents,
                pending_tasks=pending_tasks,
            )
            if kb_context:
                prompt = kb_context + "\n\n" + prompt

            # ── Generate summary ──────────────────────────────────────────
            try:
                summary, tokens_used = await self._generate(prompt, input["trace_id"])
            except Exception as exc:
                err = str(exc)
                duration = int((time.monotonic() - start) * 1000)
                try:
                    await self.log(
                        db=db,
                        trace_id=input["trace_id"],
                        status="error",
                        input_data={"date": today},
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

            result = {
                "date": today,
                "calendar_events": calendar_events,
                "overnight_research": overnight_research,
                "overnight_agents": overnight_agents,
                "pending_tasks": pending_tasks,
                "web_roundup": web_roundup,
                "summary": summary,
            }

            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="success",
                    input_data={"date": today},
                    output_data={
                        "events": len(calendar_events),
                        "agents": len(overnight_agents),
                        "tasks": len(pending_tasks),
                    },
                    tokens_used=tokens_used,
                    duration_ms=duration,
                )
            except Exception:
                pass

            output = AgentOutput(
                success=True,
                result=result,
                agent=self.name,
                duration_ms=duration,
                tokens_used=tokens_used,
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
                        "pulse",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    # ── Data gathering (all non-fatal) ────────────────────────────────

    async def _gather_calendar(self) -> List[Dict[str, str]]:
        try:
            return await _fetch_calendar_events()
        except Exception as exc:
            logger.warning("Calendar fetch failed: %s", exc)
            return []

    async def _gather_research(self) -> str:
        try:
            sem = SemanticMemoryService(get_qdrant_service(), get_embedding_service())
            hits = await sem.search_similar("[RAW:research]", limit=5)
            return "\n".join(h.get("content", "") for h in hits if h.get("content"))
        except Exception as exc:
            logger.warning("Qdrant research fetch failed: %s", exc)
            return ""

    async def _gather_overnight_agents(self, db: Any) -> List[Dict[str, str]]:
        try:
            rows = await db.fetch(
                """
                SELECT DISTINCT ON (agent)
                    agent,
                    status,
                    created_at::text AS last_run
                FROM agent_logs
                WHERE created_at >= NOW() - INTERVAL '8 hours'
                ORDER BY agent, created_at DESC
                """
            )
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("agent_logs fetch failed: %s", exc)
            return []

    async def _gather_web_roundup(self, trace_id: str) -> List[Dict[str, str]]:
        """Fetch each page in sources.yml; return list of {url,title,excerpt}.
        Each page failure is logged and skipped — the rest still render."""
        from services.browser import get_browser_service, BrowserError
        out: List[Dict[str, str]] = []
        for entry in _load_pages():
            url = entry.get("url")
            if not url:
                continue
            try:
                page = await get_browser_service().fetch(url, trace_id=trace_id)
            except BrowserError as exc:
                logger.warning(
                    "[%s] PULSE web roundup skip %s: %s", trace_id, url, exc,
                )
                continue
            out.append({
                "url": url,
                "title": page.get("title", ""),
                "excerpt": (page.get("text") or "")[:500],
            })
        return out

    async def _gather_pending_tasks(self, db: Any) -> List[Dict[str, Any]]:
        try:
            rows = await db.fetch(
                """
                SELECT title, agent, priority
                FROM tasks
                WHERE status IN ('pending', 'in_progress')
                ORDER BY priority ASC
                LIMIT 10
                """
            )
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("tasks fetch failed: %s", exc)
            return []

    # ── LLM generation with fallback ─────────────────────────────────

    async def _generate(self, prompt: str, trace_id: str) -> Tuple[str, int]:
        """Generate briefing via Llama (Ollama) with Claude Haiku fallback."""
        try:
            ollama = OllamaService()
            response = await ollama.generate(model=_MODEL, prompt=prompt)
            return response.get("response", ""), 0
        except Exception as ollama_exc:
            logger.warning(
                "[%s] Ollama unavailable (%s) — falling back to Claude",
                trace_id,
                ollama_exc,
            )

        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return content, tokens_used


# ── Google Calendar helper ────────────────────────────────────────────────

async def _fetch_calendar_events() -> List[Dict[str, str]]:
    """
    Fetch today's events from Google Calendar API.

    Requires GOOGLE_CALENDAR_ACCESS_TOKEN and GOOGLE_CALENDAR_ID env vars.
    Returns [] if token is not configured (graceful degradation).
    """
    token = os.environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN", "")
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    if not token:
        logger.info("GOOGLE_CALENDAR_ACCESS_TOKEN not set — skipping calendar")
        return []

    today = datetime.date.today()
    time_min = f"{today.isoformat()}T00:00:00Z"
    time_max = f"{today.isoformat()}T23:59:59Z"

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}
    ) as client:
        resp = await client.get(
            f"{_GOOGLE_CALENDAR_BASE}/calendars/{calendar_id}/events",
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    events = []
    for item in data.get("items", []):
        start = item.get("start", {})
        end = item.get("end", {})
        events.append({
            "title": item.get("summary", "Untitled"),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
        })
    return events


# ── Prompt builder ────────────────────────────────────────────────────────

def _build_prompt(
    today: str,
    calendar_events: List[Dict[str, str]],
    overnight_research: str,
    overnight_agents: List[Dict[str, str]],
    pending_tasks: List[Dict[str, Any]],
) -> str:
    """Assemble the full briefing prompt from all data sources."""
    lines = [_SYSTEM_PROMPT, f"\nDate: {today}\n"]

    # Calendar
    if calendar_events:
        lines.append("Today's calendar:")
        for ev in calendar_events:
            lines.append(f"  - {ev['title']} ({ev['start']} → {ev['end']})")
    else:
        lines.append("Today's calendar: No events found.")

    # Overnight research
    lines.append("\nOvernight research (from RAW):")
    lines.append(overnight_research or "  No overnight research available.")

    # Agent activity
    if overnight_agents:
        lines.append("\nOvernight agent activity:")
        for ag in overnight_agents:
            when = ag.get("last_run") or ag.get("created_at", "")
            lines.append(f"  - {ag['agent']}: {ag['status']} at {when}")
    else:
        lines.append("\nOvernight agent activity: None.")

    # Pending tasks
    if pending_tasks:
        lines.append("\nPending tasks (by priority):")
        for task in pending_tasks:
            lines.append(f"  - [{task['agent']}] {task['title']} (priority {task['priority']})")
    else:
        lines.append("\nPending tasks: None.")

    lines.append("\nGenerate the morning briefing:")
    return "\n".join(lines)
