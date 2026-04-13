"""
Tests for ReachAgent — 2-stage lead discovery + personalised outreach.

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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(task: str = "Find 3 fintech startups in Mumbai needing dev help") -> AgentInput:
    return {
        "task": task,
        "context": {},
        "trace_id": "trace-reach-001",
        "conversation_id": "conv-reach-001",
    }


def _lead(
    name: str = "Rahul Mehta",
    company: str = "PayFlow",
    title: str = "CTO",
    email: str = "rahul@payflow.io",
    website: str = "payflow.io",
    reason: str = "Hiring 3 backend devs, growing fast",
) -> dict:
    return {
        "name": name,
        "company": company,
        "title": title,
        "email": email,
        "website": website,
        "reason": reason,
    }


def _leads_json(leads: list | None = None) -> str:
    if leads is None:
        leads = [_lead()]
    return json.dumps({"leads": leads})


def _outreach_json(
    subject: str = "Quick idea for PayFlow's backend scaling",
    body: str = "Hi Rahul, I noticed PayFlow is growing fast...",
) -> str:
    return json.dumps({"subject": subject, "body": body})


def _gemini_response(text: str) -> dict:
    """Simulate a Gemini REST API response."""
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}}
        ]
    }


def _mock_httpx_post(response_json: dict):
    """Return a mock httpx response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_json
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestReachAgentInterface:
    def test_reach_agent_can_be_imported(self):
        from agents.reach.reach_agent import ReachAgent  # noqa: F401

    def test_reach_agent_extends_base_agent(self):
        from agents.reach.reach_agent import ReachAgent
        assert issubclass(ReachAgent, BaseAgent)

    def test_reach_agent_name_is_REACH(self):
        from agents.reach.reach_agent import ReachAgent
        assert ReachAgent().name == "REACH"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.reach.reach_agent import ReachAgent
        agent = ReachAgent()
        with patch("agents.reach.reach_agent.httpx.AsyncClient"), \
             patch("agents.reach.reach_agent.OllamaService"), \
             patch("agents.reach.reach_agent.get_db_service"):
            coro = agent.process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()


# ─────────────────────────────────────────────
# AgentOutput structure
# ─────────────────────────────────────────────

class TestReachAgentOutput:
    async def test_returns_success_true_on_happy_path(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert result["success"] is True

    async def test_agent_name_is_REACH_in_output(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert result["agent"] == "REACH"

    async def test_result_contains_criteria(self):
        from agents.reach.reach_agent import ReachAgent
        task = "Find SaaS founders in Bangalore"
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input(task=task))
        assert result["result"]["criteria"] == task

    async def test_result_contains_total(self):
        from agents.reach.reach_agent import ReachAgent
        leads = [_lead(name=f"Lead {i}") for i in range(3)]
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json(leads))
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert result["result"]["total"] == 3

    async def test_result_contains_leads_list(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert isinstance(result["result"]["leads"], list)
        assert len(result["result"]["leads"]) == 1

    async def test_each_lead_has_required_fields(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        lead = result["result"]["leads"][0]
        for field in ("name", "company", "title", "email", "website", "reason"):
            assert field in lead

    async def test_each_lead_has_outreach(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        lead = result["result"]["leads"][0]
        assert "outreach" in lead
        assert "subject" in lead["outreach"]
        assert "body" in lead["outreach"]


# ─────────────────────────────────────────────
# Stage 1 — Gemini discovery
# ─────────────────────────────────────────────

class TestReachAgentDiscovery:
    async def test_uses_gemini_flash_model(self):
        from agents.reach.reach_agent import _DISCOVERY_MODEL
        assert "gemini" in _DISCOVERY_MODEL.lower()
        assert "flash" in _DISCOVERY_MODEL.lower()

    async def test_gemini_called_once_for_discovery(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            mock_client, mock_post = _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            await ReachAgent().process(_make_input())
        mock_post.assert_called_once()

    async def test_criteria_sent_to_gemini(self):
        from agents.reach.reach_agent import ReachAgent
        task = "Find React developers in Pune"
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            mock_client, mock_post = _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            await ReachAgent().process(_make_input(task=task))
        call_args = mock_post.call_args
        body = call_args[1].get("json") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("json", {})
        body_str = json.dumps(body)
        assert task in body_str

    async def test_returns_error_when_gemini_fails(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService"), \
             patch("agents.reach.reach_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Gemini API error"))
            mock_client_cls.return_value = mock_client
            result = await ReachAgent().process(_make_input())
        assert result["success"] is False

    async def test_returns_error_when_gemini_returns_no_leads(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService"), \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, json.dumps({"leads": []}))
            result = await ReachAgent().process(_make_input())
        assert result["success"] is False
        assert result["error"] is not None

    async def test_tokens_used_zero_gemini_is_free(self):
        """Gemini Flash 2.5 free tier — no token cost to track."""
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert result["tokens_used"] == 0


# ─────────────────────────────────────────────
# Stage 2 — Qwen personalisation
# ─────────────────────────────────────────────

class TestReachAgentPersonalisation:
    async def test_ollama_called_once_per_lead(self):
        from agents.reach.reach_agent import ReachAgent
        leads = [_lead(name=f"Person {i}") for i in range(3)]
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json(leads))
            mock_ollama, mock_generate = _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            await ReachAgent().process(_make_input())
        assert mock_generate.call_count == 3

    async def test_lead_info_included_in_personalisation_prompt(self):
        from agents.reach.reach_agent import ReachAgent
        lead = _lead(name="Priya Shah", company="DataVault")
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json([lead]))
            mock_ollama, mock_generate = _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            await ReachAgent().process(_make_input())
        call_kwargs = mock_generate.call_args
        prompt = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        assert "Priya Shah" in prompt or "DataVault" in prompt

    async def test_personalisation_failure_is_non_fatal(self):
        """If Qwen fails for one lead, that lead gets outreach=None, others succeed."""
        from agents.reach.reach_agent import ReachAgent
        leads = [_lead(name="Lead A"), _lead(name="Lead B")]
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.anthropic.AsyncAnthropic") as mock_anthropic_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json(leads))
            # Ollama fails for ALL leads
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
            mock_ollama_cls.return_value = mock_ollama
            # Claude also fails
            mock_claude = MagicMock()
            mock_claude.messages = MagicMock()
            mock_claude.messages.create = AsyncMock(side_effect=Exception("also down"))
            mock_anthropic_cls.return_value = mock_claude

            result = await ReachAgent().process(_make_input())

        # Overall still succeeds — we have leads even without outreach
        assert result["success"] is True
        for lead in result["result"]["leads"]:
            assert lead["outreach"] is None


# ─────────────────────────────────────────────
# Claude fallback for personalisation
# ─────────────────────────────────────────────

class TestReachAgentClaudeFallback:
    async def test_falls_back_to_claude_when_ollama_fails(self):
        from agents.reach.reach_agent import ReachAgent

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=_outreach_json())]
        mock_resp.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_claude.messages.create = AsyncMock(return_value=mock_resp)

        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await ReachAgent().process(_make_input())

        assert result["success"] is True
        lead = result["result"]["leads"][0]
        assert lead["outreach"] is not None
        assert "subject" in lead["outreach"]

    async def test_claude_fallback_tokens_tracked(self):
        from agents.reach.reach_agent import ReachAgent

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=_outreach_json())]
        mock_resp.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_claude.messages.create = AsyncMock(return_value=mock_resp)

        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await ReachAgent().process(_make_input())

        assert result["tokens_used"] == 150  # 100 + 50


# ─────────────────────────────────────────────
# Approval gate
# ─────────────────────────────────────────────

class TestReachAgentApprovalGate:
    async def test_requires_approval_true_on_success(self):
        """Sending outreach emails is irreversible — always gate."""
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert result["requires_approval"] is True

    async def test_approval_prompt_mentions_lead_count(self):
        from agents.reach.reach_agent import ReachAgent
        leads = [_lead(name=f"L{i}") for i in range(4)]
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json(leads))
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        assert "4" in result["approval_prompt"]

    async def test_approval_prompt_mentions_outreach(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())
            result = await ReachAgent().process(_make_input())
        prompt_lower = result["approval_prompt"].lower()
        assert "email" in prompt_lower or "send" in prompt_lower or "outreach" in prompt_lower

    async def test_requires_approval_false_on_error(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService"), \
             patch("agents.reach.reach_agent.get_db_service"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Gemini down"))
            mock_client_cls.return_value = mock_client
            result = await ReachAgent().process(_make_input())
        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Lead / outreach parsing
# ─────────────────────────────────────────────

class TestLeadsParsing:
    def test_parses_clean_leads_json(self):
        from agents.reach.reach_agent import _parse_leads
        leads = _parse_leads(_leads_json())
        assert len(leads) == 1
        assert leads[0]["name"] == "Rahul Mehta"

    def test_parses_leads_in_code_fence(self):
        from agents.reach.reach_agent import _parse_leads
        fenced = f"```json\n{_leads_json()}\n```"
        leads = _parse_leads(fenced)
        assert leads is not None
        assert len(leads) == 1

    def test_parses_leads_embedded_in_prose(self):
        from agents.reach.reach_agent import _parse_leads
        prose = f"Here are your leads:\n{_leads_json()}\nLet me know!"
        leads = _parse_leads(prose)
        assert leads is not None

    def test_returns_none_on_invalid_json(self):
        from agents.reach.reach_agent import _parse_leads
        assert _parse_leads("not json") is None

    def test_returns_none_when_leads_key_missing(self):
        from agents.reach.reach_agent import _parse_leads
        assert _parse_leads(json.dumps({"results": []})) is None

    def test_returns_none_on_empty_string(self):
        from agents.reach.reach_agent import _parse_leads
        assert _parse_leads("") is None


class TestOutreachParsing:
    def test_parses_clean_outreach_json(self):
        from agents.reach.reach_agent import _parse_outreach
        outreach = _parse_outreach(_outreach_json())
        assert outreach["subject"] == "Quick idea for PayFlow's backend scaling"
        assert "Rahul" in outreach["body"]

    def test_parses_outreach_in_code_fence(self):
        from agents.reach.reach_agent import _parse_outreach
        fenced = f"```json\n{_outreach_json()}\n```"
        outreach = _parse_outreach(fenced)
        assert outreach is not None

    def test_returns_none_on_invalid_json(self):
        from agents.reach.reach_agent import _parse_outreach
        assert _parse_outreach("sorry, cannot help") is None

    def test_returns_none_when_subject_missing(self):
        from agents.reach.reach_agent import _parse_outreach
        assert _parse_outreach(json.dumps({"body": "hi"})) is None


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestReachAgentLogging:
    async def test_log_called_on_success(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service") as mock_db_svc:
            mock_db = AsyncMock()
            mock_db_svc.return_value = mock_db
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())

            agent = ReachAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())

        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_on_gemini_failure(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService"), \
             patch("agents.reach.reach_agent.get_db_service") as mock_db_svc:
            mock_db = AsyncMock()
            mock_db_svc.return_value = mock_db
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Gemini down"))
            mock_client_cls.return_value = mock_client

            agent = ReachAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())

        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        from agents.reach.reach_agent import ReachAgent
        with patch("agents.reach.reach_agent.httpx.AsyncClient") as mock_client_cls, \
             patch("agents.reach.reach_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.reach.reach_agent.get_db_service"):
            _setup_gemini_mock(mock_client_cls, _leads_json())
            _setup_ollama_mock(mock_ollama_cls, _outreach_json())

            agent = ReachAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB dead")
                result = await agent.process(_make_input())

        assert result["success"] is True


# ─────────────────────────────────────────────
# Test setup helpers
# ─────────────────────────────────────────────

def _setup_gemini_mock(mock_client_cls, leads_json_str: str):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_resp = _mock_httpx_post(_gemini_response(leads_json_str))
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value = mock_client
    return mock_client, mock_client.post


def _setup_ollama_mock(mock_ollama_cls, outreach_json_str: str):
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value={"response": outreach_json_str})
    mock_ollama_cls.return_value = mock_ollama
    return mock_ollama, mock_ollama.generate
