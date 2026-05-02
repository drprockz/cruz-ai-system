"""
RawAgent — 3 AM tech research and dependency scan.

Modes (via context["mode"]):
  "research"     — Llama 3.1 8B summarises a tech topic, stores in Qdrant
  "dependencies" — runs pip outdated, Llama analyses output, stores in Qdrant
  default        — "research"

Primary model: Llama 3.1 8B via Ollama (local, zero cost)
Fallback: Claude Haiku when Ollama unavailable

Output (AgentOutput.result):
  {
    "mode":    "research" | "dependencies",
    "topic":   "<topic researched or package manager>",
    "summary": "<LLM-generated summary>",
    "stored":  True | False,
    "items":   [<research points or outdated package names>],
  }

requires_approval=False — research and scanning are internal/read-only.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid as _uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import anthropic
import yaml

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.embedding import get_embedding_service
from services.knowledge_base import get_kb_service
from services.ollama import OllamaService
from services.qdrant import get_qdrant_service
from services.semantic_memory import SemanticMemoryService

logger = logging.getLogger("cruz.agents.RAW")

_MODEL = "llama3.1:8b"

_RESEARCH_SYSTEM = (
    "You are RAW, a technical research assistant. "
    "Given a tech topic, write a concise but thorough research summary covering: "
    "current state, recent developments, key players, and practical implications. "
    "Format as structured bullet points. Be specific and technical."
)

_DEPS_SYSTEM = (
    "You are RAW, a dependency analysis assistant. "
    "Given output from 'pip list --outdated', identify: "
    "which packages need urgent security updates, which are safe to defer, "
    "and any breaking changes to watch for. "
    "Return a concise markdown summary with action items."
)


_SOURCES_PATH = str(Path(__file__).parent / "sources.yml")


def _load_sources() -> dict:
    """Load sources.yml; return dict with 'rss' and 'pages' keys."""
    try:
        with open(_SOURCES_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return {
            "rss": data.get("rss") or [],
            "pages": data.get("pages") or [],
        }
    except FileNotFoundError:
        return {"rss": [], "pages": []}


async def _summarise(text: str, *, model: str = "llama3.1:8b") -> str:
    """Summarise raw page text with the local Ollama model.

    Module-level so tests can monkeypatch it cleanly.
    """
    svc = OllamaService()
    resp = await svc.generate(
        model=model,
        prompt=(
            "Summarise the following page text in 4-6 bullet points. "
            "Focus on factual claims, names, dates, and concrete actions:\n\n"
            f"{text[:6000]}"
        ),
    )
    return (resp.get("response") or "").strip()


class RawAgent(BaseAgent):
    """
    Tech research and dependency scan agent.

    Runs at 3 AM via ARQ cron. Uses Llama 3.1 8B locally (zero cost).
    Stores findings in Qdrant for PULSE and other agents to query.
    requires_approval=False — internal read-only work.
    """

    KNOWLEDGE_RINGS: List[str] = ["cruz_activities", "cruz_domain_knowledge"]

    def __init__(self) -> None:
        super().__init__()
        self.name = "RAW"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        mode = input["context"].get("mode", "research")
        topic = input["context"].get("topic", "") or input["task"]
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
            if mode == "dependencies":
                summary, items, tokens_used = await self._scan_dependencies(
                    input["trace_id"], kb_context=kb_context
                )
                topic = "pip-dependencies"
            else:
                # Default: research mode
                mode = "research"
                summary, tokens_used = await self._research(
                    topic, input["trace_id"], kb_context=kb_context
                )
                items = []

            # Store finding in Qdrant semantic memory
            stored = False
            try:
                sem = SemanticMemoryService(get_qdrant_service(), get_embedding_service())
                await sem.store(
                    id=str(_uuid.uuid4()),
                    role="assistant",
                    content=f"[RAW:{mode}] {topic}\n\n{summary}",
                    conversation_id=f"raw-{mode}",
                )
                stored = True
            except Exception as store_exc:
                logger.warning("[%s] Qdrant store failed: %s", input["trace_id"], store_exc)

            result = {
                "mode": mode,
                "topic": topic,
                "summary": summary,
                "stored": stored,
                "items": items,
            }

            # ── Write domain knowledge to cruz_domain_knowledge ring ─────
            # RAW is the canonical producer of long-lived research findings.
            # We write the summary as one entry, plus each parsed item
            # (e.g. outdated package) as its own entry so each gets a
            # distinct embedding/topic.
            try:
                await kb.write_domain_knowledge(
                    content=str(summary)[:1000],
                    topic=topic,
                    source="raw_agent",
                    trace_id=input["trace_id"],
                )
                for item in items:
                    await kb.write_domain_knowledge(
                        content=f"{topic}: {item}",
                        topic=f"{topic}:{item}",
                        source="raw_agent",
                        trace_id=input["trace_id"],
                    )
            except Exception as kb_exc:
                logger.warning(
                    "[%s] write_domain_knowledge failed (non-fatal): %s",
                    input["trace_id"],
                    kb_exc,
                )

            # ── Browser-sourced pages branch (new in SP4) ───────────────────
            # Only when mode == "research" — dependencies mode is unrelated.
            if mode == "research":
                from services.browser import (
                    get_browser_service,
                    BrowserError,
                )
                sources = _load_sources()
                for entry in sources.get("pages", []):
                    url = entry.get("url")
                    if not url:
                        continue
                    try:
                        page = await get_browser_service().fetch(
                            url, trace_id=input["trace_id"]
                        )
                    except BrowserError as exc:
                        logger.warning(
                            "[%s] RAW skipping %s: %s",
                            input["trace_id"], url, exc,
                        )
                        continue
                    try:
                        page_summary = await _summarise(
                            page["text"],
                            model=entry.get("summarize_with", _MODEL),
                        )
                    except Exception as exc:
                        logger.warning(
                            "[%s] RAW _summarise failed for %s: %s",
                            input["trace_id"], url, exc,
                        )
                        continue
                    try:
                        await kb.write_domain_knowledge(
                            content=page_summary[:1000],
                            topic=entry.get("topic") or page.get("title") or url,
                            source="raw_agent",
                            trace_id=input["trace_id"],
                        )
                    except Exception as kb_exc:
                        logger.warning(
                            "[%s] write_domain_knowledge failed for %s: %s",
                            input["trace_id"], url, kb_exc,
                        )

            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="success",
                    input_data={"mode": mode, "topic": topic},
                    output_data={"stored": stored, "items_count": len(items)},
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

        except Exception as exc:
            err = str(exc)
            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"mode": mode, "topic": topic},
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

        finally:
            # ── KB activity record (fire-and-forget; never raises) ────────
            try:
                if output is not None:
                    await kb.record_agent_activity(
                        "raw",
                        input["task"],
                        str(output.get("result", ""))[:200],
                        output["success"],
                        input["trace_id"],
                        project_id=input["context"].get("project_id"),
                        tokens_used=output.get("tokens_used"),
                    )
            except Exception:
                pass

    # ── Research mode ─────────────────────────────────────────────────────

    async def _research(
        self, topic: str, trace_id: str, kb_context: str = ""
    ) -> Tuple[str, int]:
        """Summarise a tech topic using Llama, fall back to Claude Haiku."""
        prompt = f"{_RESEARCH_SYSTEM}\n\nTopic: {topic}"
        if kb_context:
            prompt = kb_context + "\n\n" + prompt
        return await self._generate(prompt, trace_id)

    # ── Dependencies mode ─────────────────────────────────────────────────

    async def _scan_dependencies(
        self, trace_id: str, kb_context: str = ""
    ) -> Tuple[str, List[str], int]:
        """Run pip list --outdated, analyse with Llama, return summary + items."""
        pip_output = await self._run_pip_outdated()
        items = _parse_outdated_packages(pip_output)
        prompt = f"{_DEPS_SYSTEM}\n\npip list --outdated output:\n{pip_output or '(no outdated packages)'}"
        if kb_context:
            prompt = kb_context + "\n\n" + prompt
        summary, tokens_used = await self._generate(prompt, trace_id)
        return summary, items, tokens_used

    async def _run_pip_outdated(self) -> str:
        """Run pip list --outdated and return stdout."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pip", "list", "--outdated", "--format=columns",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode(errors="replace")
        except Exception as exc:
            logger.warning("pip outdated failed: %s", exc)
            return ""

    # ── LLM generation with fallback ─────────────────────────────────────

    async def _generate(self, prompt: str, trace_id: str) -> Tuple[str, int]:
        """Generate text via Llama (Ollama) with Claude Haiku fallback."""
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
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return content, tokens_used


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_outdated_packages(pip_output: str) -> List[str]:
    """Extract package names from pip list --outdated output."""
    packages: List[str] = []
    for line in pip_output.splitlines():
        parts = line.split()
        # Skip header lines (Package, Version, Latest, Type)
        if len(parts) >= 3 and parts[0] not in ("Package", "--------"):
            packages.append(parts[0])
    return packages
