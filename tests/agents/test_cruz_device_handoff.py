"""
Tests for CruzAgent cross-device handoff integration.

When a device switch is detected:
  - CruzAgent must inject a handoff note into the messages list so Claude
    knows the user has switched devices and can proactively surface context
  - The handoff note must name both the previous and current device
  - DeviceHandoffService.publish_switch() must be called

When no device is provided or no switch detected:
  - Normal flow — no handoff injection
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from agents.base_agent import AgentInput


def _make_input(device: str | None = "ipad") -> AgentInput:
    return {
        "task": "What's on my calendar today?",
        "context": {"device": device},
        "trace_id": "trace-handoff-001",
        "conversation_id": "conv-handoff-001",
    }


def _mock_claude_end_turn(text: str = "Here's your calendar."):
    """Return a minimal mock Anthropic response with stop_reason=end_turn."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [content_block]
    response.usage = MagicMock(input_tokens=50, output_tokens=20)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _mock_conv_service():
    svc = AsyncMock()
    svc.get_or_create_conversation = AsyncMock(return_value="conv-handoff-001")
    svc.load_history = AsyncMock(return_value=[])
    svc.save_exchange = AsyncMock()
    return svc


def _mock_sem_service():
    svc = AsyncMock()
    svc.search_similar = AsyncMock(return_value=[])
    svc.store = AsyncMock()
    return svc


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Handoff injection when device switches
# ---------------------------------------------------------------------------

class TestCruzDeviceSwitchInjection:
    @pytest.mark.asyncio
    async def test_handoff_note_injected_on_device_switch(self):
        """When switch detected, a handoff message appears in the Claude call."""
        from agents.cruz.cruz_agent import CruzAgent
        agent = CruzAgent()
        claude = _mock_claude_end_turn()

        handoff_svc = AsyncMock()
        handoff_svc.detect_switch = AsyncMock(return_value=(True, "phone"))
        handoff_svc.publish_switch = AsyncMock()
        handoff_svc.set_device = AsyncMock()

        with (
            patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.cruz.cruz_agent.ConversationService", return_value=_mock_conv_service()),
            patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_mock_sem_service()),
            patch("agents.cruz.cruz_agent.get_db_service", return_value=_mock_db()),
            patch("agents.cruz.cruz_agent.get_qdrant_service"),
            patch("agents.cruz.cruz_agent.get_embedding_service"),
            patch("agents.cruz.cruz_agent.DeviceHandoffService", return_value=handoff_svc),
            patch("agents.cruz.cruz_agent.get_redis_service"),
        ):
            await agent.process(_make_input(device="ipad"))

        # Inspect the messages passed to Claude
        messages_sent = claude.messages.create.call_args.kwargs["messages"]
        all_content = " ".join(
            m.get("content", "") if isinstance(m.get("content"), str) else str(m.get("content", ""))
            for m in messages_sent
        )
        assert "phone" in all_content or "ipad" in all_content

    @pytest.mark.asyncio
    async def test_handoff_note_mentions_previous_device(self):
        """Handoff context must name the previous device."""
        from agents.cruz.cruz_agent import CruzAgent
        agent = CruzAgent()
        claude = _mock_claude_end_turn()

        handoff_svc = AsyncMock()
        handoff_svc.detect_switch = AsyncMock(return_value=(True, "phone"))
        handoff_svc.publish_switch = AsyncMock()

        with (
            patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.cruz.cruz_agent.ConversationService", return_value=_mock_conv_service()),
            patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_mock_sem_service()),
            patch("agents.cruz.cruz_agent.get_db_service", return_value=_mock_db()),
            patch("agents.cruz.cruz_agent.get_qdrant_service"),
            patch("agents.cruz.cruz_agent.get_embedding_service"),
            patch("agents.cruz.cruz_agent.DeviceHandoffService", return_value=handoff_svc),
            patch("agents.cruz.cruz_agent.get_redis_service"),
        ):
            await agent.process(_make_input(device="ipad"))

        messages_sent = claude.messages.create.call_args.kwargs["messages"]
        all_content = " ".join(str(m) for m in messages_sent)
        assert "phone" in all_content

    @pytest.mark.asyncio
    async def test_publish_switch_called_on_switch(self):
        """publish_switch() must be called when a device switch is detected."""
        from agents.cruz.cruz_agent import CruzAgent
        agent = CruzAgent()
        claude = _mock_claude_end_turn()

        handoff_svc = AsyncMock()
        handoff_svc.detect_switch = AsyncMock(return_value=(True, "phone"))
        handoff_svc.publish_switch = AsyncMock()

        with (
            patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.cruz.cruz_agent.ConversationService", return_value=_mock_conv_service()),
            patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_mock_sem_service()),
            patch("agents.cruz.cruz_agent.get_db_service", return_value=_mock_db()),
            patch("agents.cruz.cruz_agent.get_qdrant_service"),
            patch("agents.cruz.cruz_agent.get_embedding_service"),
            patch("agents.cruz.cruz_agent.DeviceHandoffService", return_value=handoff_svc),
            patch("agents.cruz.cruz_agent.get_redis_service"),
        ):
            await agent.process(_make_input(device="ipad"))

        handoff_svc.publish_switch.assert_called_once_with(
            "conv-handoff-001", "phone", "ipad"
        )


# ---------------------------------------------------------------------------
# No injection when no switch
# ---------------------------------------------------------------------------

class TestCruzNoSwitchFlow:
    @pytest.mark.asyncio
    async def test_no_handoff_when_same_device(self):
        """Same device as last time → normal flow, publish_switch not called."""
        from agents.cruz.cruz_agent import CruzAgent
        agent = CruzAgent()
        claude = _mock_claude_end_turn()

        handoff_svc = AsyncMock()
        handoff_svc.detect_switch = AsyncMock(return_value=(False, "ipad"))
        handoff_svc.publish_switch = AsyncMock()

        with (
            patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.cruz.cruz_agent.ConversationService", return_value=_mock_conv_service()),
            patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_mock_sem_service()),
            patch("agents.cruz.cruz_agent.get_db_service", return_value=_mock_db()),
            patch("agents.cruz.cruz_agent.get_qdrant_service"),
            patch("agents.cruz.cruz_agent.get_embedding_service"),
            patch("agents.cruz.cruz_agent.DeviceHandoffService", return_value=handoff_svc),
            patch("agents.cruz.cruz_agent.get_redis_service"),
        ):
            out = await agent.process(_make_input(device="ipad"))

        handoff_svc.publish_switch.assert_not_called()
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_no_handoff_when_device_not_provided(self):
        """No device in context → DeviceHandoffService not used."""
        from agents.cruz.cruz_agent import CruzAgent
        agent = CruzAgent()
        claude = _mock_claude_end_turn()

        handoff_svc = AsyncMock()
        handoff_svc.detect_switch = AsyncMock(return_value=(False, None))
        handoff_svc.publish_switch = AsyncMock()

        with (
            patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.cruz.cruz_agent.ConversationService", return_value=_mock_conv_service()),
            patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_mock_sem_service()),
            patch("agents.cruz.cruz_agent.get_db_service", return_value=_mock_db()),
            patch("agents.cruz.cruz_agent.get_qdrant_service"),
            patch("agents.cruz.cruz_agent.get_embedding_service"),
            patch("agents.cruz.cruz_agent.DeviceHandoffService", return_value=handoff_svc),
            patch("agents.cruz.cruz_agent.get_redis_service"),
        ):
            out = await agent.process(_make_input(device=None))

        handoff_svc.detect_switch.assert_not_called()
        handoff_svc.publish_switch.assert_not_called()
        assert out["success"] is True

    @pytest.mark.asyncio
    async def test_handoff_failure_is_non_fatal(self):
        """DeviceHandoffService error must not crash CruzAgent."""
        from agents.cruz.cruz_agent import CruzAgent
        agent = CruzAgent()
        claude = _mock_claude_end_turn("All good.")

        handoff_svc = AsyncMock()
        handoff_svc.detect_switch = AsyncMock(side_effect=Exception("Redis down"))
        handoff_svc.publish_switch = AsyncMock()

        with (
            patch("agents.cruz.cruz_agent.anthropic.AsyncAnthropic", return_value=claude),
            patch("agents.cruz.cruz_agent.ConversationService", return_value=_mock_conv_service()),
            patch("agents.cruz.cruz_agent.SemanticMemoryService", return_value=_mock_sem_service()),
            patch("agents.cruz.cruz_agent.get_db_service", return_value=_mock_db()),
            patch("agents.cruz.cruz_agent.get_qdrant_service"),
            patch("agents.cruz.cruz_agent.get_embedding_service"),
            patch("agents.cruz.cruz_agent.DeviceHandoffService", return_value=handoff_svc),
            patch("agents.cruz.cruz_agent.get_redis_service"),
        ):
            out = await agent.process(_make_input(device="ipad"))

        assert out["success"] is True
