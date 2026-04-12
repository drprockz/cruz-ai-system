"""
Tests for ConversationService — load/save conversation history.

ConversationService wraps the PostgreSQL conversations + messages tables
and exposes two methods:
  - load_history(conversation_id) → list of {role, content} dicts for Claude
  - save_exchange(conversation_id, user_task, assistant_result) → persists turn

RED phase — must fail before production code exists.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.conversation import ConversationService


def _make_db(fetch_result=None, fetchrow_result=None):
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=fetch_result or [])
    db.fetchrow = AsyncMock(return_value=fetchrow_result)
    db.execute = AsyncMock(return_value="INSERT 0 1")
    return db


class TestConversationServiceInterface:
    def test_conversation_service_can_be_instantiated(self):
        db = _make_db()
        service = ConversationService(db)
        assert service is not None

    def test_has_load_history_method(self):
        db = _make_db()
        assert hasattr(ConversationService(db), "load_history")

    def test_has_save_exchange_method(self):
        db = _make_db()
        assert hasattr(ConversationService(db), "save_exchange")

    def test_has_get_or_create_conversation_method(self):
        db = _make_db()
        assert hasattr(ConversationService(db), "get_or_create_conversation")


class TestLoadHistory:
    async def test_returns_empty_list_for_new_conversation(self):
        db = _make_db(fetch_result=[])
        service = ConversationService(db)

        history = await service.load_history("new-conv-id")

        assert history == []

    async def test_returns_messages_in_claude_format(self):
        """Each row from DB must be converted to {role, content} dict."""
        rows = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "2+2 equals 4."},
        ]
        db = _make_db(fetch_result=rows)
        service = ConversationService(db)

        history = await service.load_history("conv-123")

        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "What is 2+2?"}
        assert history[1] == {"role": "assistant", "content": "2+2 equals 4."}

    async def test_queries_by_conversation_id(self):
        db = _make_db(fetch_result=[])
        service = ConversationService(db)

        await service.load_history("conv-abc-123")

        db.fetch.assert_called_once()
        call_args = str(db.fetch.call_args)
        assert "conv-abc-123" in call_args

    async def test_orders_messages_chronologically(self):
        """Messages must be in created_at ASC order for Claude context."""
        db = _make_db(fetch_result=[])
        service = ConversationService(db)

        await service.load_history("conv-1")

        query = db.fetch.call_args[0][0]
        assert "ORDER BY" in query.upper()
        assert "ASC" in query.upper() or "created_at" in query.lower()

    async def test_limits_to_50_messages(self):
        """Only last 50 messages loaded — keeps Claude context cost bounded."""
        db = _make_db(fetch_result=[])
        service = ConversationService(db)

        await service.load_history("conv-1")

        query = db.fetch.call_args[0][0]
        assert "50" in query or "LIMIT" in query.upper()

    async def test_strips_extra_db_fields(self):
        """DB rows may have id, created_at etc. — only role+content go to Claude."""
        rows = [
            {
                "id": 1,
                "conversation_id": "conv-1",
                "role": "user",
                "content": "Hello",
                "metadata": None,
                "created_at": "2026-04-13T00:00:00",
            }
        ]
        db = _make_db(fetch_result=rows)
        service = ConversationService(db)

        history = await service.load_history("conv-1")

        assert history[0] == {"role": "user", "content": "Hello"}
        assert "id" not in history[0]
        assert "created_at" not in history[0]


class TestSaveExchange:
    async def test_saves_user_message(self):
        db = _make_db()
        service = ConversationService(db)

        await service.save_exchange(
            conversation_id="conv-1",
            user_task="What time is it?",
            assistant_result="It is 3pm.",
        )

        # execute should be called at least twice (user + assistant messages)
        assert db.execute.call_count >= 2

    async def test_saves_assistant_message(self):
        db = _make_db()
        service = ConversationService(db)

        await service.save_exchange("conv-1", "Hello", "Hi there!")

        all_calls = " ".join(str(c) for c in db.execute.call_args_list)
        assert "assistant" in all_calls

    async def test_save_includes_conversation_id(self):
        db = _make_db()
        service = ConversationService(db)

        await service.save_exchange("conv-xyz-456", "task", "result")

        all_calls = " ".join(str(c) for c in db.execute.call_args_list)
        assert "conv-xyz-456" in all_calls

    async def test_save_includes_user_content(self):
        db = _make_db()
        service = ConversationService(db)

        await service.save_exchange("conv-1", "unique-user-task-text", "answer")

        all_calls = " ".join(str(c) for c in db.execute.call_args_list)
        assert "unique-user-task-text" in all_calls

    async def test_save_includes_assistant_content(self):
        db = _make_db()
        service = ConversationService(db)

        await service.save_exchange("conv-1", "question", "unique-assistant-answer-text")

        all_calls = " ".join(str(c) for c in db.execute.call_args_list)
        assert "unique-assistant-answer-text" in all_calls


class TestGetOrCreateConversation:
    async def test_returns_existing_conversation_id(self):
        """If conversation already exists, return its ID unchanged."""
        existing = {"id": "conv-existing-001"}
        db = _make_db(fetchrow_result=existing)
        service = ConversationService(db)

        conv_id = await service.get_or_create_conversation("conv-existing-001")

        assert conv_id == "conv-existing-001"

    async def test_creates_new_conversation_when_not_found(self):
        """If conversation_id not in DB, insert a new row and return the id."""
        db = _make_db(fetchrow_result=None)  # not found
        service = ConversationService(db)

        conv_id = await service.get_or_create_conversation("brand-new-id")

        # execute called to INSERT the new conversation
        db.execute.assert_called_once()
        assert conv_id == "brand-new-id"

    async def test_new_conversation_insert_uses_provided_id(self):
        db = _make_db(fetchrow_result=None)
        service = ConversationService(db)

        await service.get_or_create_conversation("my-specific-id")

        insert_call = str(db.execute.call_args)
        assert "my-specific-id" in insert_call
