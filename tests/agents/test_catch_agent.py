"""
Tests for CatchAgent — meeting transcription + summarisation specialist.

CatchAgent:
  - Accepts audio bytes (via context["audio_bytes"]) OR pre-transcribed text (via task)
  - Transcribes audio using VoicePipeline (Whisper Large v3, already in services/voice.py)
  - Summarises transcript using Llama 3.1 8B via Ollama
  - Falls back to Claude Haiku when Ollama is unavailable
  - Returns structured meeting notes: {title, summary, action_items, decisions, transcript}
  - ALWAYS requires human approval before creating Notion pages or Linear tickets
  - Calls self.log() on success AND error paths

Meeting notes structure:
  {
    "title": "<meeting title>",
    "summary": "<2-3 sentence summary>",
    "action_items": ["<owner>: <task>", ...],
    "decisions": ["<decision>", ...],
    "transcript": "<full transcript text>"
  }
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentInput, AgentOutput, BaseAgent


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_input(
    task: str = "Summarise the AMA client sync meeting",
    audio_bytes: bytes | None = None,
) -> AgentInput:
    ctx = {}
    if audio_bytes is not None:
        ctx["audio_bytes"] = audio_bytes
    return {
        "task": task,
        "context": ctx,
        "trace_id": "trace-catch-001",
        "conversation_id": "conv-catch-001",
    }


def _meeting_notes_json(
    title: str = "AMA Client Sync",
    summary: str = "Discussed website timeline and deliverables.",
    action_items: list | None = None,
    decisions: list | None = None,
) -> str:
    return json.dumps({
        "title": title,
        "summary": summary,
        "action_items": action_items or ["Darshan: deploy staging by Friday"],
        "decisions": decisions or ["Go with React over Vue"],
    })


def _mock_ollama_response(raw_text: str) -> dict:
    return {"response": raw_text}


def _fake_transcript() -> str:
    return (
        "Ateet: So what's the timeline for the homepage? "
        "Darshan: I'll have staging ready by Friday. "
        "Ateet: Great, let's go with React then."
    )


# ─────────────────────────────────────────────
# Interface
# ─────────────────────────────────────────────

class TestCatchAgentInterface:
    def test_catch_agent_can_be_imported(self):
        from agents.catch.catch_agent import CatchAgent  # noqa: F401

    def test_catch_agent_extends_base_agent(self):
        from agents.catch.catch_agent import CatchAgent
        assert issubclass(CatchAgent, BaseAgent)

    def test_catch_agent_name_is_CATCH(self):
        from agents.catch.catch_agent import CatchAgent
        assert CatchAgent().name == "CATCH"

    def test_process_is_coroutine(self):
        import asyncio
        from agents.catch.catch_agent import CatchAgent
        agent = CatchAgent()
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            coro = agent.process(_make_input())
            assert asyncio.iscoroutine(coro)
            coro.close()


# ─────────────────────────────────────────────
# AgentOutput structure
# ─────────────────────────────────────────────

class TestCatchAgentOutput:
    async def test_returns_success_true_on_happy_path(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["success"] is True

    async def test_agent_name_is_CATCH_in_output(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["agent"] == "CATCH"

    async def test_result_contains_title(self):
        from agents.catch.catch_agent import CatchAgent
        notes_json = _meeting_notes_json(title="Shooterista Sprint Review")
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(notes_json)
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["result"]["title"] == "Shooterista Sprint Review"

    async def test_result_contains_summary(self):
        from agents.catch.catch_agent import CatchAgent
        notes_json = _meeting_notes_json(summary="Sprint went well, all items shipped.")
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(notes_json)
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["result"]["summary"] == "Sprint went well, all items shipped."

    async def test_result_contains_action_items_list(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert isinstance(result["result"]["action_items"], list)

    async def test_result_contains_decisions_list(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert isinstance(result["result"]["decisions"], list)

    async def test_result_contains_transcript(self):
        """Transcript must be preserved in result for Notion page body."""
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input(task=_fake_transcript()))
        assert "transcript" in result["result"]
        assert isinstance(result["result"]["transcript"], str)

    async def test_duration_ms_is_non_negative(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0


# ─────────────────────────────────────────────
# Audio transcription path
# ─────────────────────────────────────────────

class TestCatchAgentTranscription:
    async def test_transcribes_audio_bytes_from_context(self):
        """When context contains audio_bytes, CATCH must call VoicePipeline.transcribe."""
        from agents.catch.catch_agent import CatchAgent
        fake_audio = b"RIFF....fake wav bytes"

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline") as mock_vp_cls:
            mock_vp = AsyncMock()
            mock_vp.transcribe = AsyncMock(return_value=_fake_transcript())
            mock_vp_cls.return_value = mock_vp

            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama

            await CatchAgent().process(_make_input(audio_bytes=fake_audio))

        mock_vp.transcribe.assert_called_once_with(fake_audio)

    async def test_transcript_from_audio_passed_to_llm(self):
        """The transcript from Whisper must be sent to Ollama for summarisation."""
        from agents.catch.catch_agent import CatchAgent
        fake_audio = b"fake audio"
        transcript = "Darshan: we ship Friday. Ateet: agreed."

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline") as mock_vp_cls:
            mock_vp = AsyncMock()
            mock_vp.transcribe = AsyncMock(return_value=transcript)
            mock_vp_cls.return_value = mock_vp

            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama

            await CatchAgent().process(_make_input(audio_bytes=fake_audio))

        call_kwargs = mock_ollama.generate.call_args
        prompt = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        assert transcript in prompt

    async def test_uses_task_as_transcript_when_no_audio(self):
        """Without audio_bytes in context, use the task string directly as the transcript."""
        from agents.catch.catch_agent import CatchAgent
        transcript = "Darshan: homepage by Friday. Ateet: ship it."

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline") as mock_vp_cls:
            mock_vp = AsyncMock()
            mock_vp_cls.return_value = mock_vp

            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama

            await CatchAgent().process(_make_input(task=transcript))

        # VoicePipeline.transcribe should NOT be called — no audio bytes
        mock_vp.transcribe.assert_not_called()

        call_kwargs = mock_ollama.generate.call_args
        prompt = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        assert transcript in prompt

    async def test_transcript_stored_in_result(self):
        """Transcript returned by Whisper must appear in result['transcript']."""
        from agents.catch.catch_agent import CatchAgent
        fake_audio = b"wav bytes"
        transcript = "This is the meeting transcript."

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline") as mock_vp_cls:
            mock_vp = AsyncMock()
            mock_vp.transcribe = AsyncMock(return_value=transcript)
            mock_vp_cls.return_value = mock_vp

            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama

            result = await CatchAgent().process(_make_input(audio_bytes=fake_audio))

        assert result["result"]["transcript"] == transcript

    async def test_empty_transcript_returns_error(self):
        """If Whisper returns empty string (silent audio), return failure."""
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService"), \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline") as mock_vp_cls:
            mock_vp = AsyncMock()
            mock_vp.transcribe = AsyncMock(return_value="")
            mock_vp_cls.return_value = mock_vp
            result = await CatchAgent().process(_make_input(audio_bytes=b"silence"))
        assert result["success"] is False
        assert "transcript" in result["error"].lower() or "audio" in result["error"].lower()


# ─────────────────────────────────────────────
# Ollama primary — Llama 3.1 8B
# ─────────────────────────────────────────────

class TestCatchAgentOllamaPrimary:
    async def test_uses_llama_model(self):
        """CATCH must use llama3.1:8b — distinct from Qwen used by ECHO and PM."""
        from agents.catch.catch_agent import _SUMMARISE_MODEL
        assert "llama" in _SUMMARISE_MODEL.lower()

    async def test_ollama_called_for_summarisation(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            await CatchAgent().process(_make_input())
        mock_ollama.generate.assert_called_once()

    async def test_tokens_used_zero_for_local_model(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["tokens_used"] == 0


# ─────────────────────────────────────────────
# Claude fallback
# ─────────────────────────────────────────────

class TestCatchAgentClaudeFallback:
    async def test_falls_back_to_claude_when_ollama_raises(self):
        from agents.catch.catch_agent import CatchAgent

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=_meeting_notes_json())]
        mock_resp.usage = MagicMock(input_tokens=300, output_tokens=150)
        mock_claude.messages.create = AsyncMock(return_value=mock_resp)

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())

        assert result["success"] is True
        assert result["result"]["title"] is not None

    async def test_claude_fallback_counts_tokens(self):
        from agents.catch.catch_agent import CatchAgent

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=_meeting_notes_json())]
        mock_resp.usage = MagicMock(input_tokens=300, output_tokens=150)
        mock_claude.messages.create = AsyncMock(return_value=mock_resp)

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("Ollama down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())

        assert result["tokens_used"] == 450  # 300 in + 150 out

    async def test_returns_error_when_both_fail(self):
        from agents.catch.catch_agent import CatchAgent

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=Exception("Claude also down"))

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())

        assert result["success"] is False
        assert result["error"] is not None


# ─────────────────────────────────────────────
# Approval gate — always required
# ─────────────────────────────────────────────

class TestCatchAgentApprovalGate:
    async def test_requires_approval_true_on_success(self):
        """Creating Notion pages and Linear tickets is irreversible — always gate."""
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["requires_approval"] is True

    async def test_approval_prompt_mentions_notion(self):
        """User must know where notes will be saved."""
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert "notion" in result["approval_prompt"].lower()

    async def test_approval_prompt_mentions_action_item_count(self):
        """User must see how many action items were extracted before confirming."""
        from agents.catch.catch_agent import CatchAgent
        notes_json = _meeting_notes_json(action_items=["A: do X", "B: do Y", "C: do Z"])
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(notes_json)
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert "3" in result["approval_prompt"]

    async def test_requires_approval_false_on_error(self):
        from agents.catch.catch_agent import CatchAgent
        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=Exception("all down"))

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["requires_approval"] is False


# ─────────────────────────────────────────────
# Meeting notes parsing
# ─────────────────────────────────────────────

class TestMeetingNotesParsing:
    def test_parses_clean_json(self):
        from agents.catch.catch_agent import _parse_notes
        notes = _parse_notes(_meeting_notes_json())
        assert notes["title"] == "AMA Client Sync"
        assert notes["summary"] == "Discussed website timeline and deliverables."
        assert isinstance(notes["action_items"], list)
        assert isinstance(notes["decisions"], list)

    def test_parses_json_in_code_fence(self):
        from agents.catch.catch_agent import _parse_notes
        fenced = f"```json\n{_meeting_notes_json()}\n```"
        notes = _parse_notes(fenced)
        assert notes is not None
        assert notes["title"] == "AMA Client Sync"

    def test_parses_json_embedded_in_prose(self):
        from agents.catch.catch_agent import _parse_notes
        prose = f"Here are the meeting notes:\n{_meeting_notes_json()}\nLet me know if I missed anything."
        notes = _parse_notes(prose)
        assert notes is not None
        assert "action_items" in notes

    def test_returns_none_on_invalid_json(self):
        from agents.catch.catch_agent import _parse_notes
        assert _parse_notes("no JSON here") is None

    def test_returns_none_when_title_missing(self):
        from agents.catch.catch_agent import _parse_notes
        incomplete = json.dumps({"summary": "s", "action_items": [], "decisions": []})
        assert _parse_notes(incomplete) is None

    def test_returns_none_when_action_items_missing(self):
        from agents.catch.catch_agent import _parse_notes
        incomplete = json.dumps({"title": "t", "summary": "s", "decisions": []})
        assert _parse_notes(incomplete) is None

    def test_returns_none_on_empty_string(self):
        from agents.catch.catch_agent import _parse_notes
        assert _parse_notes("") is None

    def test_action_items_defaults_to_empty_list(self):
        """action_items may be an empty list — that's valid (some meetings have none)."""
        from agents.catch.catch_agent import _parse_notes
        notes_json = json.dumps({
            "title": "Quick sync",
            "summary": "Brief check-in.",
            "action_items": [],
            "decisions": [],
        })
        notes = _parse_notes(notes_json)
        assert notes is not None
        assert notes["action_items"] == []


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

class TestCatchAgentLogging:
    async def test_log_called_on_success(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service") as mock_db_svc, \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_db = AsyncMock()
            mock_db_svc.return_value = mock_db
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama

            agent = CatchAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())

        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "success"

    async def test_log_called_on_error(self):
        from agents.catch.catch_agent import CatchAgent

        mock_claude = MagicMock()
        mock_claude.messages = MagicMock()
        mock_claude.messages.create = AsyncMock(side_effect=Exception("all down"))

        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.anthropic.AsyncAnthropic", return_value=mock_claude), \
             patch("agents.catch.catch_agent.get_db_service") as mock_db_svc, \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_db = AsyncMock()
            mock_db_svc.return_value = mock_db
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=ConnectionError("down"))
            mock_ollama_cls.return_value = mock_ollama

            agent = CatchAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                await agent.process(_make_input())

        mock_log.assert_called_once()
        assert mock_log.call_args[1]["status"] == "error"

    async def test_log_failure_does_not_crash_agent(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response(_meeting_notes_json())
            )
            mock_ollama_cls.return_value = mock_ollama

            agent = CatchAgent()
            with patch.object(agent, "log", new_callable=AsyncMock) as mock_log:
                mock_log.side_effect = Exception("DB dead")
                result = await agent.process(_make_input())

        assert result["success"] is True


# ─────────────────────────────────────────────
# Parse failure path
# ─────────────────────────────────────────────

class TestCatchAgentParseFailure:
    async def test_returns_error_when_llm_returns_garbage(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response("I cannot summarise this.")
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["success"] is False

    async def test_requires_approval_false_on_parse_failure(self):
        from agents.catch.catch_agent import CatchAgent
        with patch("agents.catch.catch_agent.OllamaService") as mock_ollama_cls, \
             patch("agents.catch.catch_agent.get_db_service"), \
             patch("agents.catch.catch_agent.VoicePipeline"):
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(
                return_value=_mock_ollama_response("garbage output")
            )
            mock_ollama_cls.return_value = mock_ollama
            result = await CatchAgent().process(_make_input())
        assert result["requires_approval"] is False
