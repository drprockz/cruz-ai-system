"""
ReachAgent — 2-stage lead discovery + personalised outreach.

Stage 1 — Discovery (Gemini Flash 2.5 via REST):
  Given a criteria string, Gemini returns a list of leads:
  [{name, company, title, email, website, reason}]

Stage 2 — Personalisation (Qwen 2.5 Coder 14B via Ollama):
  For each lead, Qwen drafts a personalised outreach email:
  {subject, body}

Output structure:
  {
    "criteria": "<original criteria>",
    "total":    <int>,
    "leads": [
      {
        "name":    "<full name>",
        "company": "<company>",
        "title":   "<job title>",
        "email":   "<email or empty string>",
        "website": "<domain or empty string>",
        "reason":  "<why they're a good fit>",
        "outreach": {
          "subject": "<email subject>",
          "body":    "<email body>"
        }
      }
    ]
  }

Rules:
  - requires_approval=True always — sending outreach emails is irreversible
  - Personalisation falls back to Claude Haiku if Ollama is unavailable
  - Gemini failure → success=False (no leads to work with)
  - Personalisation failure for a single lead is non-fatal — that lead gets outreach=None
  - self.log() on success and error paths
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import anthropic
import httpx

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service
from services.ollama import OllamaService

logger = logging.getLogger("cruz.agents.REACH")

_DISCOVERY_MODEL = "gemini-2.5-flash"
_PERSONALISE_MODEL = "qwen2.5-coder:14b"

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_DISCOVERY_SYSTEM = """\
You are a lead generation specialist. Given a criteria description, find real potential clients.

Respond ONLY with valid JSON — no prose, no markdown, no explanation.

JSON format:
{
  "leads": [
    {
      "name":    "<full name of decision maker>",
      "company": "<company name>",
      "title":   "<job title>",
      "email":   "<email address or empty string if unknown>",
      "website": "<company domain or empty string>",
      "reason":  "<1-2 sentences: why they are a good fit>"
    }
  ]
}

Guidelines:
- Return 3-10 leads that closely match the criteria
- Prioritise decision makers (CTO, CEO, Founder, Head of Engineering)
- reason should explain specifically why they need help right now
- Empty string for email/website if genuinely unknown
- Do not invent fake people — use plausible, realistic leads"""

_PERSONALISE_SYSTEM = """\
You are REACH, an expert outreach copywriter. Draft a personalised cold email for a specific lead.

Respond ONLY with valid JSON — no prose, no markdown, no explanation.

JSON format:
{
  "subject": "<compelling email subject line>",
  "body":    "<full email body — 3-4 short paragraphs>"
}

Guidelines:
- Subject: concise, specific, no clickbait
- Opening: reference something specific about their company or role
- Value prop: 1-2 sentences on what you offer and why it's relevant to them
- CTA: one clear, low-friction ask (15-min call, quick question, etc.)
- Closing: professional sign-off
- Tone: peer-to-peer, not sales-y
- Length: 150-250 words total"""


class ReachAgent(BaseAgent):
    """
    2-stage lead discovery and outreach personalisation agent.

    Stage 1: Gemini Flash 2.5 discovers leads matching the criteria.
    Stage 2: Qwen 14B drafts a personalised outreach email per lead.
    Always returns requires_approval=True — sending emails is external and irreversible.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "REACH"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        db = get_db_service()
        total_tokens = 0

        # ── Stage 1: Discover leads via Gemini ───────────────────────────
        try:
            leads = await self._discover_leads(input["task"])
        except Exception as exc:
            err = f"Lead discovery failed: {exc}"
            logger.warning("[%s] %s", input["trace_id"], err)
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

        if not leads:
            err = "No leads found matching the criteria"
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

        # ── Stage 2: Personalise outreach per lead ────────────────────────
        enriched_leads: List[Dict[str, Any]] = []
        for lead in leads:
            outreach, tokens = await self._personalise_lead(lead, input["task"], input["trace_id"])
            total_tokens += tokens
            enriched_leads.append({**lead, "outreach": outreach})

        # ── Build result ──────────────────────────────────────────────────
        total = len(enriched_leads)
        result = {
            "criteria": input["task"],
            "total": total,
            "leads": enriched_leads,
        }

        approval_prompt = (
            f"Send outreach emails to {total} lead{'s' if total != 1 else ''}?\n"
            f"  Criteria: {input['task']}\n"
            f"  Leads with outreach drafts: {total}\n\n"
            f"Reply 'yes' to send or 'no' to discard."
        )

        duration = int((time.monotonic() - start) * 1000)
        try:
            await self.log(
                db=db,
                trace_id=input["trace_id"],
                status="success",
                input_data={"task": input["task"]},
                output_data={"total": total, "leads": [l["name"] for l in leads]},
                tokens_used=total_tokens,
                duration_ms=duration,
            )
        except Exception:
            pass

        return AgentOutput(
            success=True,
            result=result,
            agent=self.name,
            duration_ms=duration,
            tokens_used=total_tokens,
            error=None,
            requires_approval=True,
            approval_prompt=approval_prompt,
        )

    async def _discover_leads(self, criteria: str) -> Optional[List[Dict[str, Any]]]:
        """Call Gemini Flash 2.5 REST API to discover leads. Returns list or raises."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        url = f"{_GEMINI_API_BASE}/{_DISCOVERY_MODEL}:generateContent?key={api_key}"
        prompt = f"{_DISCOVERY_SYSTEM}\n\nCriteria: {criteria}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "contents": [
                        {"parts": [{"text": prompt}]}
                    ]
                },
            )
            response.raise_for_status()
            data = response.json()

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_leads(raw_text)

    async def _personalise_lead(
        self,
        lead: Dict[str, Any],
        criteria: str,
        trace_id: str,
    ) -> tuple[Optional[Dict[str, Any]], int]:
        """
        Personalise outreach for a single lead.

        Returns (outreach_dict, tokens_used). If both Ollama and Claude fail,
        returns (None, 0) — non-fatal per the contract.
        """
        prompt = (
            f"{_PERSONALISE_SYSTEM}\n\n"
            f"Lead:\n"
            f"  Name: {lead.get('name', '')}\n"
            f"  Company: {lead.get('company', '')}\n"
            f"  Title: {lead.get('title', '')}\n"
            f"  Website: {lead.get('website', '')}\n"
            f"  Why they're a fit: {lead.get('reason', '')}\n\n"
            f"Outreach criteria / sender context: {criteria}"
        )

        # Try Qwen via Ollama first
        try:
            ollama = OllamaService()
            response = await ollama.generate(model=_PERSONALISE_MODEL, prompt=prompt)
            raw_text: str = response.get("response", "")
            outreach = _parse_outreach(raw_text)
            if outreach is not None:
                return outreach, 0  # local — no cloud token cost
        except Exception as ollama_exc:
            logger.warning(
                "[%s] Ollama personalisation failed for %s (%s) — trying Claude",
                trace_id,
                lead.get("name", "?"),
                ollama_exc,
            )

        # Fallback to Claude Haiku
        try:
            client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            claude_response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = claude_response.content[0].text
            tokens_used = (
                claude_response.usage.input_tokens + claude_response.usage.output_tokens
            )
            outreach = _parse_outreach(raw_text)
            return outreach, tokens_used
        except Exception as claude_exc:
            logger.warning(
                "[%s] Claude personalisation also failed for %s (%s) — outreach=None",
                trace_id,
                lead.get("name", "?"),
                claude_exc,
            )
            return None, 0


# ─────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────

def _parse_leads(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Extract leads list from a model response.

    Handles: pure JSON, ```json fenced, JSON embedded in prose.
    Required: top-level "leads" key containing a list.
    Returns None on parse failure.
    """
    if not text or not text.strip():
        return None

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    candidate = _try_parse_leads(text.strip())
    if candidate is not None:
        return candidate

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return _try_parse_leads(brace_match.group(0))

    return None


def _try_parse_leads(text: str) -> Optional[List[Dict[str, Any]]]:
    """Parse JSON and validate it has a 'leads' list."""
    try:
        data = json.loads(text)
        if "leads" in data and isinstance(data["leads"], list):
            return [
                {
                    "name": str(l.get("name", "")),
                    "company": str(l.get("company", "")),
                    "title": str(l.get("title", "")),
                    "email": str(l.get("email", "")),
                    "website": str(l.get("website", "")),
                    "reason": str(l.get("reason", "")),
                }
                for l in data["leads"]
            ]
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None


def _parse_outreach(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract outreach JSON from a model response.

    Required fields: subject, body.
    Returns None on parse failure.
    """
    if not text or not text.strip():
        return None

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)

    candidate = _try_parse_outreach(text.strip())
    if candidate is not None:
        return candidate

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return _try_parse_outreach(brace_match.group(0))

    return None


def _try_parse_outreach(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON and validate it has subject and body."""
    try:
        data = json.loads(text)
        if "subject" in data and "body" in data:
            return {
                "subject": str(data["subject"]),
                "body": str(data["body"]),
            }
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None
