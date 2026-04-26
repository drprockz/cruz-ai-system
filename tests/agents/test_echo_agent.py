"""
Tests for EchoAgent — email/message drafting with approval gate.

EchoAgent:
  - Uses Qwen 2.5 Coder 14B via OllamaService (local, no cloud cost)
  - Drafts emails/messages from a natural-language task
  - ALWAYS sets requires_approval=True — nothing is sent without user confirmation
  - Returns a structured draft: {to, subject, body}
  - approval_prompt summarises what will be sent and to whom

RED phase — must fail before production code exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput
from agents.echo.echo_agent import EchoAgent, EmailDraft


# ─────────────────────────────────────────────
# KB service mock — autouse, applies to every test in this module
# ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_kb_service():
    """Mock KnowledgeBaseService for all ECHO tests."""
    mock_kb = MagicMock()
    mock_kb.build_agent_context = AsyncMock(return_value="")
    mock_kb.record_agent_activity = AsyncMock()
    with patch("agents.echo.echo_agent.get_kb_service", return_value=mock_kb):
        yield mock_kb


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(task: str = "draft an email to John about the project delay") -> AgentInput:
    return {
        "task": task,
        "context": {},
        "trace_id": "trace-echo-001",
        "conversation_id": "conv-001",
    }


def _make_ollama_json_response(to: str, subject: str, body: str) -> dict:
    """Simulate Ollama returning a JSON draft inside its response field."""
    import json
    payload = json.dumps({"to": to, "subject": subject, "body": body})
    return {"response": payload, "done": True}


def _make_ollama_text_response(text: str) -> dict:
    """Simulate Ollama returning free-form text (fallback parsing path)."""
    return {"response": text, "done": True}


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestEchoAgentInterface:
    def test_echo_agent_subclasses_base_agent(self):
        from agents.base_agent import BaseAgent
        assert issubclass(EchoAgent, BaseAgent)

    def test_echo_agent_can_be_instantiated(self):
        assert EchoAgent() is not None

    def test_echo_agent_name_is_echo(self):
        assert EchoAgent().name == "ECHO"

    def test_echo_agent_has_process_method(self):
        assert callable(EchoAgent().process)


# ─────────────────────────────────────────────
# EmailDraft TypedDict / dataclass
# ─────────────────────────────────────────────

class TestEmailDraft:
    def test_email_draft_has_to_field(self):
        draft: EmailDraft = {"to": "john@example.com", "subject": "Hi", "body": "Hello"}
        assert draft["to"] == "john@example.com"

    def test_email_draft_has_subject_field(self):
        draft: EmailDraft = {"to": "a@b.com", "subject": "Update", "body": "Body here"}
        assert draft["subject"] == "Update"

    def test_email_draft_has_body_field(self):
        draft: EmailDraft = {"to": "a@b.com", "subject": "S", "body": "The body text"}
        assert draft["body"] == "The body text"


# ─────────────────────────────────────────────
# Core process() behaviour
# ─────────────────────────────────────────────

class TestEchoProcess:
    async def test_process_returns_success_true(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "john@example.com", "Project delay update", "Hi John, ..."
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert result["success"] is True

    async def test_process_sets_agent_name_to_echo(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "Subject", "Body"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert result["agent"] == "ECHO"

    async def test_process_returns_draft_as_result(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "client@acme.com", "Project delay", "Dear Client, the project is delayed."
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        draft = result["result"]
        assert draft["to"] == "client@acme.com"
        assert draft["subject"] == "Project delay"
        assert "delayed" in draft["body"]

    async def test_process_records_duration_ms(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    async def test_process_uses_ollama_not_claude(self):
        """EchoAgent must call OllamaService.generate, not anthropic."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "x@y.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama) as MockOllama:
            with patch("agents.echo.echo_agent.anthropic", None):  # anthropic must not be used
                result = await agent.process(_make_input())

        mock_ollama.generate.assert_called_once()
        assert result["success"] is True


# ─────────────────────────────────────────────
# HARD RULE: approval gate always fires
# ─────────────────────────────────────────────

class TestEchoApprovalGate:
    async def test_requires_approval_is_always_true(self):
        """The approval gate is unconditional — no path bypasses it."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "boss@company.com", "Resign", "I quit."
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input("draft resignation email"))

        assert result["requires_approval"] is True

    async def test_approval_prompt_is_not_none(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "client@x.com", "Update", "Body"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert result["approval_prompt"] is not None
        assert len(result["approval_prompt"]) > 0

    async def test_approval_prompt_contains_recipient(self):
        """The user must see who will receive the email in the approval prompt."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "ateet@ama.com", "Invoice", "Please find attached..."
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input("send invoice to ateet"))

        assert "ateet@ama.com" in result["approval_prompt"]

    async def test_approval_prompt_contains_subject(self):
        """The user must see the subject line in the approval prompt."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "hr@company.com", "Leave request for Monday", "Hi HR, ..."
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input("request leave for Monday"))

        assert "Leave request for Monday" in result["approval_prompt"]

    async def test_tokens_used_is_zero(self):
        """Ollama is local — no cloud tokens consumed."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert result["tokens_used"] == 0


# ─────────────────────────────────────────────
# Ollama model selection
# ─────────────────────────────────────────────

class TestEchoModelSelection:
    async def test_calls_qwen_model(self):
        """ECHO must use qwen2.5-coder:14b, not a cloud model."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            await agent.process(_make_input())

        call_kwargs = mock_ollama.generate.call_args
        model_used = call_kwargs[1].get("model") or call_kwargs[0][0]
        assert "qwen" in str(model_used).lower()

    async def test_prompt_includes_task(self):
        """The prompt sent to Ollama must include the user's task."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            await agent.process(_make_input("email Sarah about the launch delay"))

        call_kwargs = mock_ollama.generate.call_args
        prompt_sent = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        assert "Sarah" in prompt_sent or "launch delay" in prompt_sent


# ─────────────────────────────────────────────
# Draft parsing — robustness
# ─────────────────────────────────────────────

class TestEchoDraftParsing:
    async def test_parses_valid_json_response(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "pm@client.com", "Sprint update", "Hi, sprint 3 completed."
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input("update client on sprint"))

        assert result["result"]["to"] == "pm@client.com"
        assert result["result"]["subject"] == "Sprint update"

    async def test_handles_json_embedded_in_text(self):
        """Ollama sometimes wraps JSON in prose — agent must still parse it."""
        import json
        payload = json.dumps({
            "to": "dev@team.com",
            "subject": "Code review request",
            "body": "Please review PR #42."
        })
        messy_response = f"Sure! Here is the draft:\n```json\n{payload}\n```"

        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value={"response": messy_response, "done": True})

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input("ask dev team to review PR 42"))

        assert result["success"] is True
        assert result["result"]["to"] == "dev@team.com"

    async def test_falls_back_gracefully_on_unparseable_response(self):
        """If Ollama returns something unparseable, return success=False with error."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value={"response": "I don't understand.", "done": True})

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input("some task"))

        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# Error handling
# ─────────────────────────────────────────────

class TestEchoErrorHandling:
    async def test_returns_failure_when_ollama_is_down(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(
            side_effect=Exception("Connection refused — Ollama not running")
        )

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert result["success"] is False
        assert result["error"] is not None
        assert result["requires_approval"] is False

    async def test_error_result_is_none(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=Exception("timeout"))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            result = await agent.process(_make_input())

        assert result["result"] is None


# ─────────────────────────────────────────────
# Agent logging
# ─────────────────────────────────────────────

class TestEchoAgentLogging:
    async def test_echo_calls_self_log_on_success(self):
        """EchoAgent must log to agent_logs after a successful draft."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "Subject", "Body"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        mock_log.assert_called()

    async def test_echo_logs_with_success_status(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process(_make_input())

        assert "success" in str(mock_log.call_args)

    async def test_echo_logs_with_error_status_on_failure(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(side_effect=Exception("Ollama down"))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            result = await agent.process(_make_input())

        assert result["success"] is False
        mock_log.assert_called()
        assert "error" in str(mock_log.call_args)

    async def test_echo_logs_trace_id(self):
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch.object(agent, "log", new=AsyncMock()) as mock_log:
            await agent.process({
                "task": "draft email",
                "context": {},
                "trace_id": "unique-echo-trace-xyz",
                "conversation_id": "conv-001",
            })

        assert "unique-echo-trace-xyz" in str(mock_log.call_args)


# ─────────────────────────────────────────────
# Claude fallback when Ollama unavailable
# ─────────────────────────────────────────────

class TestEchoClaudeFallback:
    async def test_falls_back_to_claude_when_ollama_unavailable(self):
        """When Ollama raises ConnectionError, ECHO must try Claude instead."""
        import json
        draft_json = json.dumps({
            "to": "client@example.com",
            "subject": "Project update",
            "body": "Hi, here is the update.",
        })

        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(
            side_effect=ConnectionError("Ollama not running")
        )

        mock_claude_msg = MagicMock()
        mock_claude_msg.content = [MagicMock(text=draft_json)]

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(return_value=mock_claude_msg)

        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.anthropic.AsyncAnthropic", return_value=mock_claude):
            result = await agent.process(_make_input("email client about project"))

        assert result["success"] is True
        assert result["requires_approval"] is True
        assert result["result"]["to"] == "client@example.com"

    async def test_fallback_result_still_requires_approval(self):
        """Approval gate must still fire even when Claude drafted the email."""
        import json
        draft_json = json.dumps({
            "to": "boss@work.com",
            "subject": "Leave request",
            "body": "I need tomorrow off.",
        })

        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(
            side_effect=ConnectionError("Ollama down")
        )

        mock_claude_msg = MagicMock()
        mock_claude_msg.content = [MagicMock(text=draft_json)]

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(return_value=mock_claude_msg)

        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.anthropic.AsyncAnthropic", return_value=mock_claude):
            result = await agent.process(_make_input())

        assert result["requires_approval"] is True

    async def test_returns_failure_when_both_ollama_and_claude_fail(self):
        """If both Ollama and Claude fail, return success=False with error."""
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(
            side_effect=ConnectionError("Ollama down")
        )

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(
            side_effect=Exception("Claude API error")
        )

        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.anthropic.AsyncAnthropic", return_value=mock_claude):
            result = await agent.process(_make_input())

        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# R7 — Send mode (context["send"]=True)
# ─────────────────────────────────────────────

def _make_send_input(
    task: str = "draft an email to ateet@ama.com about the project delay",
    send: bool = True,
    to: str = None,
) -> AgentInput:
    ctx = {"send": send}
    if to is not None:
        ctx["to"] = to
    return {
        "task": task,
        "context": ctx,
        "trace_id": "trace-echo-send",
        "conversation_id": "conv-send",
    }


def _mock_email_service(result=None, raises=None):
    """Build a mock EmailService.send AsyncMock."""
    svc = MagicMock()
    if raises is not None:
        svc.send = AsyncMock(side_effect=raises)
    else:
        svc.send = AsyncMock(return_value=result or {"sent": True, "message_id": "sg-1"})
    return svc


@pytest.mark.asyncio
class TestEchoSendMode:
    async def test_send_true_calls_email_service_with_draft(self):
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response(
                to="ateet@ama.com", subject="Delay update", body="Pushing by 2 days."
            )
        )
        email_svc = _mock_email_service()
        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            await agent.process(_make_send_input())

        email_svc.send.assert_called_once()
        kwargs = email_svc.send.call_args.kwargs
        assert kwargs["to"] == "ateet@ama.com"
        assert kwargs["subject"] == "Delay update"
        assert kwargs["body"] == "Pushing by 2 days."

    async def test_send_true_returns_requires_approval_false(self):
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response("a@b.com", "s", "b")
        )
        email_svc = _mock_email_service()
        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            result = await agent.process(_make_send_input())

        assert result["requires_approval"] is False

    async def test_send_true_result_includes_sent_and_message_id(self):
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response("a@b.com", "s", "b")
        )
        email_svc = _mock_email_service(result={"sent": True, "message_id": "sg-xyz"})
        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            result = await agent.process(_make_send_input())

        assert result["result"]["sent"] is True
        assert result["result"]["message_id"] == "sg-xyz"

    async def test_send_failure_returns_success_false(self):
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response("a@b.com", "s", "b")
        )
        email_svc = _mock_email_service(
            raises=RuntimeError("SendGrid send failed: HTTP 401"),
        )
        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            result = await agent.process(_make_send_input())

        assert result["success"] is False
        assert "SendGrid" in (result["error"] or "")
        assert result["requires_approval"] is False

    async def test_context_to_overrides_draft_to(self):
        """Explicit context['to'] takes precedence over what the LLM chose."""
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response(
                to="wrong@example.com", subject="s", body="b"
            )
        )
        email_svc = _mock_email_service()
        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            await agent.process(
                _make_send_input(to="ateet@ama.com")
            )

        kwargs = email_svc.send.call_args.kwargs
        assert kwargs["to"] == "ateet@ama.com"

    async def test_send_false_is_default_unchanged(self):
        """Without context['send'], ECHO still drafts + approves (legacy behavior)."""
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response("a@b.com", "s", "b")
        )
        agent = EchoAgent()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService") as email_cls:
            result = await agent.process(_make_input())

        assert result["requires_approval"] is True
        email_cls.assert_not_called()  # no EmailService ever instantiated

    async def test_send_logs_sent_status_on_success(self):
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response("a@b.com", "s", "b")
        )
        email_svc = _mock_email_service()
        agent = EchoAgent()
        agent.log = AsyncMock()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            await agent.process(_make_send_input())

        agent.log.assert_called_once()
        assert agent.log.call_args.kwargs["status"] == "success"

    async def test_send_logs_error_status_on_send_failure(self):
        mock_ollama = MagicMock()
        mock_ollama.generate = AsyncMock(
            return_value=_make_ollama_json_response("a@b.com", "s", "b")
        )
        email_svc = _mock_email_service(raises=RuntimeError("SendGrid 500"))
        agent = EchoAgent()
        agent.log = AsyncMock()

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama), \
             patch("agents.echo.echo_agent.get_db_service"), \
             patch("agents.echo.echo_agent.EmailService", return_value=email_svc):
            await agent.process(_make_send_input())

        agent.log.assert_called_once()
        assert agent.log.call_args.kwargs["status"] == "error"


# ─────────────────────────────────────────────
# Knowledge Base integration
# ─────────────────────────────────────────────


class TestEchoKnowledgeBase:
    async def test_echo_calls_kb_build_context(self, mock_kb_service):
        """build_agent_context and record_agent_activity must each fire once per process()."""
        agent = EchoAgent()
        mock_ollama = AsyncMock()
        mock_ollama.generate = AsyncMock(return_value=_make_ollama_json_response(
            "a@b.com", "S", "B"
        ))

        with patch("agents.echo.echo_agent.OllamaService", return_value=mock_ollama):
            await agent.process(_make_input())

        mock_kb_service.build_agent_context.assert_awaited_once()
        mock_kb_service.record_agent_activity.assert_awaited_once()

    def test_echo_declares_knowledge_rings(self):
        """KNOWLEDGE_RINGS must be declared on the class."""
        assert EchoAgent.KNOWLEDGE_RINGS == [
            "cruz_activities",
            "cruz_projects_docs",
            "cruz_user_patterns",
        ]
