"""
MarkAgent — documentation generation specialist.

Modes (via context["doc_type"]):
  "openapi"   — generate OpenAPI/Swagger YAML spec from source code
  "jsdoc"     — generate JSDoc comments for JS/TS source code
  "readme"    — generate a README.md for a project
  "changelog" — generate a changelog entry from commit messages

Primary model: Qwen 2.5 Coder 14B via Ollama (local, zero token cost).
Fallback: Claude Haiku when Ollama is unavailable.

Output (AgentOutput.result):
  {
    "doc_type": "openapi" | "jsdoc" | "readme" | "changelog",
    "content":  "<generated documentation string>",
    "project":  "<project name>",
  }

requires_approval=True — writing to GitHub or Notion is external and visible.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import anthropic

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.ollama import OllamaService

logger = logging.getLogger("cruz.agents.MARK")

_MODEL = "qwen2.5-coder:14b"

# ── System prompts per mode ──────────────────────────────────────────────────

_PROMPTS: Dict[str, str] = {
    "openapi": (
        "You are MARK, an API documentation specialist. "
        "Given source code, generate a complete OpenAPI 3.0 YAML specification. "
        "Include all endpoints, request/response schemas, and descriptions. "
        "Return ONLY valid YAML — no prose, no markdown fences."
    ),
    "jsdoc": (
        "You are MARK, a documentation specialist. "
        "Given JavaScript or TypeScript source code, add JSDoc comments to every "
        "function, class, and exported symbol. "
        "Return the COMPLETE annotated source code with JSDoc blocks added. "
        "Do not change any logic — only add comments."
    ),
    "readme": (
        "You are MARK, a technical writer. "
        "Given a project name and optional code samples, generate a professional README.md. "
        "Include: project title, description, features, installation, usage, and license. "
        "Return ONLY the markdown content."
    ),
    "changelog": (
        "You are MARK, a release engineer. "
        "Given a list of git commit messages, generate a formatted CHANGELOG entry "
        "following Keep a Changelog format (https://keepachangelog.com). "
        "Group commits into Added, Changed, Fixed, and Removed sections. "
        "Return ONLY the markdown changelog entry."
    ),
}

_SUPPORTED_TYPES = set(_PROMPTS.keys())


class MarkAgent(BaseAgent):
    """
    Documentation generation agent.

    Uses Qwen 14B via Ollama to generate OpenAPI specs, JSDoc,
    README files, and changelogs. Falls back to Claude Haiku when
    Ollama is unavailable. Always requires_approval=True — writing
    to GitHub or Notion is an external, visible action.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "MARK"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        doc_type = input["context"].get("doc_type", "")
        project = input["context"].get("project", "")

        # ── Validate doc_type ─────────────────────────────────────────────
        if doc_type not in _SUPPORTED_TYPES:
            err = (
                f"Unknown doc_type '{doc_type}'. "
                f"Supported: {', '.join(sorted(_SUPPORTED_TYPES))}."
            )
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"doc_type": doc_type, "project": project},
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

        # ── Build prompt ──────────────────────────────────────────────────
        prompt = _build_prompt(doc_type, input)

        # ── Generate docs ─────────────────────────────────────────────────
        try:
            content, tokens_used = await self._generate(prompt, input["trace_id"])
        except Exception as exc:
            err = str(exc)
            duration = int((time.monotonic() - start) * 1000)
            try:
                await self.log(
                    db=db,
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"doc_type": doc_type, "project": project},
                    output_data={"error": err},
                    tokens_used=0,
                    duration_ms=duration,
                )
            except Exception:
                pass
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=duration,
                tokens_used=0,
                error=err,
                requires_approval=False,
                approval_prompt=None,
            )

        # ── Build result ──────────────────────────────────────────────────
        result = {
            "doc_type": doc_type,
            "content": content,
            "project": project,
        }

        approval_prompt = (
            f"Publish {doc_type} documentation for '{project}'?\n"
            f"  Characters generated: {len(content)}\n\n"
            f"Reply 'yes' to write to GitHub/Notion or 'no' to discard."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"doc_type": doc_type, "project": project},
                output_data={"chars": len(content)},
                tokens_used=tokens_used,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=result,
            agent=self.name,
            duration_ms=duration,
            tokens_used=tokens_used,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    async def _generate(self, prompt: str, trace_id: str) -> Tuple[str, int]:
        """Generate documentation via Qwen (Ollama) with Claude Haiku fallback."""
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
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return content, tokens_used


# ─────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────

def _build_prompt(doc_type: str, input: AgentInput) -> str:
    """Assemble a mode-specific prompt from the agent input context."""
    system = _PROMPTS[doc_type]
    ctx = input["context"]
    project = ctx.get("project", "")
    code = ctx.get("code", input["task"])

    if doc_type == "openapi":
        return f"{system}\n\nProject: {project}\n\nSource code:\n\n{code}"

    if doc_type == "jsdoc":
        return f"{system}\n\nSource code:\n\n{code}"

    if doc_type == "readme":
        return f"{system}\n\nProject name: {project}\n\nCode sample:\n\n{code}"

    if doc_type == "changelog":
        commits = ctx.get("commits") or [input["task"]]
        commits_text = "\n".join(f"- {c}" for c in commits)
        return f"{system}\n\nProject: {project}\n\nCommits:\n{commits_text}"

    return f"{system}\n\n{input['task']}"
