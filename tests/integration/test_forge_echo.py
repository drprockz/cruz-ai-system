"""
Integration test: FORGE + ECHO end-to-end via CruzAgent.

Scenario: "Build a contact form for AMA Solutions and draft an email to
           Ateet saying it's ready."

Expected flow:
  1. CruzAgent calls Claude with FORGE + ECHO tools defined
  2. Claude responds with tool_use: [forge block, echo block]
  3. CruzAgent dispatches to ForgeAgent → code generated (success)
  4. CruzAgent dispatches to EchoAgent → email drafted (requires_approval=True)
  5. CruzAgent surfaces requires_approval=True with the email draft
  6. No email is sent — approval gate is live

These tests verify the full orchestration path without hitting real APIs.
All external calls (Claude, Ollama, DB, Qdrant) are mocked at the boundary.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput
from agents.cruz.cruz_agent import CruzAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(task: str = (
    "Build a contact form for AMA Solutions and draft an email "
    "to ateet@ama.com saying it's ready"
)) -> AgentInput:
    return {
        "task": task,
        "context": {},
        "trace_id": "trace-integration-001",
        "conversation_id": "conv-integration-001",
    }


def _tool_block(name: str, tool_id: str, task: str) -> MagicMock:
    """Simulate a Claude tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = {"task": task}
    return block


def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _claude_tool_response(*blocks) -> MagicMock:
    """Claude responds with tool_use blocks."""
    msg = MagicMock()
    msg.stop_reason = "tool_use"
    msg.content = list(blocks)
    msg.usage = MagicMock(input_tokens=500, output_tokens=200)
    return msg


def _claude_text_response(text: str) -> MagicMock:
    """Claude final text response after tool results fed back."""
    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.content = [_text_block(text)]
    msg.usage = MagicMock(input_tokens=300, output_tokens=100)
    return msg


def _forge_success(code: str = "// ContactForm.tsx generated") -> AgentOutput:
    return AgentOutput(
        success=True,
        result=code,
        agent="FORGE",
        duration_ms=800,
        tokens_used=400,
        error=None,
        requires_approval=False,
        approval_prompt=None,
    )


def _echo_approval(to: str = "ateet@ama.com", subject: str = "Contact form ready") -> AgentOutput:
    return AgentOutput(
        success=True,
        result={"to": to, "subject": subject, "body": "Hi Ateet, the contact form is ready."},
        agent="ECHO",
        duration_ms=600,
        tokens_used=0,
        error=None,
        requires_approval=True,
        approval_prompt=f"Send this email?\n  To: {to}\n  Subject: {subject}",
    )


def _make_conv_service() -> MagicMock:
    svc = AsyncMock()
    svc.load_history = AsyncMock(return_value=[])
    svc.save_exchange = AsyncMock()
    svc.get_or_create_conversation = AsyncMock(return_value="conv-integration-001")
    return svc


def _make_sem_service() -> MagicMock:
    svc = AsyncMock()
    svc.search_similar = AsyncMock(return_value=[])
    svc.store = AsyncMock()
    return svc


# ─────────────────────────────────────────────
# Core integration: FORGE then ECHO in one request
# ─────────────────────────────────────────────

class TestForgeEchoSequential:
    async def test_cruz_dispatches_forge_and_echo(self):
        """CruzAgent must call both ForgeAgent and EchoAgent when Claude requests both."""
        forge_block = _tool_block("forge", "tu_forge_01", "Build a contact form")
        echo_block = _tool_block("echo", "tu_echo_01", "Email ateet@ama.com it's ready")

        claude_response = _claude_tool_response(forge_block, echo_block)

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(return_value=claude_response)

        mock_forge = AsyncMock(return_value=_forge_success())
        mock_echo = AsyncMock(return_value=_echo_approval())

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", mock_forge), \
             patch("agents.echo.echo_agent.EchoAgent.process", mock_echo):
            result = await agent.process(_make_input())

        mock_forge.assert_called_once()
        mock_echo.assert_called_once()

    async def test_approval_gate_surfaces_when_echo_requires_it(self):
        """When ECHO requires approval, CruzAgent must return requires_approval=True."""
        forge_block = _tool_block("forge", "tu_forge_02", "Build contact form")
        echo_block = _tool_block("echo", "tu_echo_02", "Email Ateet it's ready")

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(
            return_value=_claude_tool_response(forge_block, echo_block)
        )

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", AsyncMock(return_value=_forge_success())), \
             patch("agents.echo.echo_agent.EchoAgent.process", AsyncMock(return_value=_echo_approval())):
            result = await agent.process(_make_input())

        assert result["requires_approval"] is True

    async def test_approval_prompt_contains_email_recipient(self):
        """The approval prompt shown to user must name who will receive the email."""
        forge_block = _tool_block("forge", "tu_forge_03", "Build contact form")
        echo_block = _tool_block("echo", "tu_echo_03", "Email ateet@ama.com")

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(
            return_value=_claude_tool_response(forge_block, echo_block)
        )

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", AsyncMock(return_value=_forge_success())), \
             patch("agents.echo.echo_agent.EchoAgent.process", AsyncMock(return_value=_echo_approval(to="ateet@ama.com"))):
            result = await agent.process(_make_input())

        assert "ateet@ama.com" in result["approval_prompt"]

    async def test_email_not_sent_without_approval(self):
        """EchoAgent.process() must be called exactly once — no auto-send path."""
        forge_block = _tool_block("forge", "tu_forge_04", "Build contact form")
        echo_block = _tool_block("echo", "tu_echo_04", "Email Ateet")

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(
            return_value=_claude_tool_response(forge_block, echo_block)
        )
        mock_echo = AsyncMock(return_value=_echo_approval())

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", AsyncMock(return_value=_forge_success())), \
             patch("agents.echo.echo_agent.EchoAgent.process", mock_echo):
            result = await agent.process(_make_input())

        # ECHO called once to draft — never called again to send
        assert mock_echo.call_count == 1
        assert result["requires_approval"] is True

    async def test_tokens_from_forge_and_echo_accumulated(self):
        """Total tokens must include forge agent tokens + claude tokens."""
        forge_block = _tool_block("forge", "tu_forge_05", "Build form")
        echo_block = _tool_block("echo", "tu_echo_05", "Email Ateet")

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(
            return_value=_claude_tool_response(forge_block, echo_block)
        )

        forge_out = _forge_success()
        forge_out["tokens_used"] = 400  # forge consumed 400 tokens

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", AsyncMock(return_value=forge_out)), \
             patch("agents.echo.echo_agent.EchoAgent.process", AsyncMock(return_value=_echo_approval())):
            result = await agent.process(_make_input())

        # Claude: 500+200=700, Forge: 400, Echo: 0 (local)
        assert result["tokens_used"] >= 700 + 400


# ─────────────────────────────────────────────
# FORGE-only path (no email requested)
# ─────────────────────────────────────────────

class TestForgeOnly:
    async def test_forge_only_completes_without_approval(self):
        """When only FORGE is called, result is returned directly — no approval gate."""
        forge_block = _tool_block("forge", "tu_forge_only", "Build a React button component")

        # Turn 1: Claude calls forge
        # Turn 2: Claude gives final text after seeing forge result
        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=[
            _claude_tool_response(forge_block),
            _claude_text_response("I built the button component. File written to Button.tsx."),
        ])

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", AsyncMock(return_value=_forge_success())):
            result = await agent.process({
                "task": "Build a React button component",
                "context": {},
                "trace_id": "trace-forge-only",
                "conversation_id": "conv-forge-only",
            })

        assert result["success"] is True
        assert result["requires_approval"] is False
        assert "button" in result["result"].lower() or "built" in result["result"].lower()

    async def test_forge_result_fed_back_to_claude(self):
        """After FORGE runs, its output must be sent back to Claude for the final response."""
        forge_block = _tool_block("forge", "tu_forge_feed", "Build a form")

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=[
            _claude_tool_response(forge_block),
            _claude_text_response("Form built successfully."),
        ])

        agent = CruzAgent()

        with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
             patch("agents.cruz.cruz_agent.get_db_service"), \
             patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
             patch("agents.cruz.cruz_agent.get_qdrant_service"), \
             patch("agents.cruz.cruz_agent.get_embedding_service"), \
             patch("agents.forge.forge_agent.ForgeAgent.process", AsyncMock(return_value=_forge_success("form code here"))):
            await agent.process({
                "task": "Build a form",
                "context": {},
                "trace_id": "trace-forge-feed",
                "conversation_id": "conv-forge-feed",
            })

        # Claude must have been called twice (once with task, once with tool result)
        assert mock_claude.messages.create.call_count == 2
        # Second call must include tool_result content
        second_call_messages = mock_claude.messages.create.call_args_list[1][1]["messages"]
        messages_str = str(second_call_messages)
        assert "tool_result" in messages_str


# ─────────────────────────────────────────────
# Real file I/O through FORGE (no Claude mock for forge internals)
# ─────────────────────────────────────────────

class TestForgeRealFileIO:
    async def test_forge_writes_file_during_cruz_orchestration(self):
        """
        Full path: CruzAgent → ForgeAgent (real) → writes actual file.
        ForgeAgent's own Claude call is mocked, but file I/O is real.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = os.path.join(tmpdir, "ContactForm.tsx")
            code = 'export function ContactForm() { return <form />; }\n'

            # CruzAgent's Claude:
            # Call 1 → forge tool use; Call 2 → final text after forge result
            forge_block = _tool_block(
                "forge", "tu_forge_real",
                f"Write a React contact form to {target_path}"
            )
            cruz_claude = MagicMock()
            cruz_claude.messages = MagicMock()
            cruz_claude.messages.create = AsyncMock(side_effect=[
                _claude_tool_response(forge_block),
                _claude_text_response("ContactForm.tsx has been written successfully."),
            ])

            # ForgeAgent's own Claude: calls write_file then ends
            write_block = MagicMock()
            write_block.type = "tool_use"
            write_block.id = "tu_write_01"
            write_block.name = "write_file"
            write_block.input = {"path": target_path, "content": code}

            forge_write_response = MagicMock()
            forge_write_response.stop_reason = "tool_use"
            forge_write_response.content = [write_block]
            forge_write_response.usage = MagicMock(input_tokens=300, output_tokens=100)

            forge_done_response = MagicMock()
            forge_done_response.stop_reason = "end_turn"
            forge_done_response.content = [MagicMock(type="text", text="ContactForm.tsx written.")]
            forge_done_response.usage = MagicMock(input_tokens=200, output_tokens=50)

            forge_claude = MagicMock()
            forge_claude.messages = MagicMock()
            forge_claude.messages.create = AsyncMock(
                side_effect=[forge_write_response, forge_done_response]
            )

            agent = CruzAgent()

            # CruzAgent's Claude is cruz_claude; ForgeAgent's Claude is forge_claude
            call_count = {"n": 0}

            def pick_client(**kwargs):
                call_count["n"] += 1
                # First instantiation → CruzAgent's client
                # Second instantiation → ForgeAgent's client
                return cruz_claude if call_count["n"] == 1 else forge_claude

            # Note: forge_agent.anthropic and cruz_agent.anthropic are the same
            # module object — one patch covers both. pick_client returns
            # cruz_claude on the 1st call (CruzAgent) and forge_claude on the 2nd (ForgeAgent).
            with patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", side_effect=pick_client), \
                 patch("agents.forge.forge_agent.get_db_service"), \
                 patch("agents.cruz.cruz_agent.ConversationService", return_value=_make_conv_service()), \
                 patch("agents.cruz.cruz_agent.get_db_service"), \
                 patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_make_sem_service()), \
                 patch("agents.cruz.cruz_agent.get_qdrant_service"), \
                 patch("agents.cruz.cruz_agent.get_embedding_service"):
                result = await agent.process({
                    "task": f"Write a React contact form to {target_path}",
                    "context": {},
                    "trace_id": "trace-real-file",
                    "conversation_id": "conv-real-file",
                })

            # The file must exist on disk
            assert Path(target_path).exists(), "ForgeAgent must have written the file"
            assert Path(target_path).read_text() == code
