"""
Tests for GET /conversations/{conversation_id}/messages.

The endpoint loads conversation history so clients can restore context
when switching devices (phone → iPad → ThinkPad).

Contract:
  - 200 + [{role, content}, ...] for an existing conversation
  - 200 + [] for a conversation with no messages (not 404)
  - 404 when the conversation_id does not exist in the DB
  - messages are in chronological order (oldest first)
  - each message has exactly role and content (no DB internals)
  - only the last 50 messages are returned

RED phase — must fail before the endpoint exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))
from main import app


def _make_conv_service(history=None, conversation_exists=True):
    """Return a mock ConversationService wired to the given history list."""
    svc = AsyncMock()
    svc.load_history = AsyncMock(return_value=history or [])
    # get_or_create returns None when conversation doesn't exist (simulate 404)
    if conversation_exists:
        svc.get_or_create_conversation = AsyncMock(return_value="conv-001")
    else:
        svc.get_or_create_conversation = AsyncMock(return_value=None)
    return svc


class TestConversationsEndpointExists:
    def test_get_conversations_messages_returns_not_405(self):
        """GET /conversations/{id}/messages must exist."""
        client = TestClient(app)
        with patch("main.ConversationService"), patch("main.get_db_service"):
            resp = client.get("/conversations/conv-001/messages")
        assert resp.status_code != 405

    def test_get_conversations_messages_is_not_404_for_existing(self):
        """A registered route must not return 404 due to missing route."""
        svc = _make_conv_service(history=[])
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/conv-001/messages")
        # 404 would mean the route itself doesn't exist
        assert resp.status_code != 404 or resp.json().get("detail") != "Not Found"


class TestConversationsEndpointSuccess:
    def test_returns_200_for_existing_conversation(self):
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        svc = _make_conv_service(history=history)
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/conv-001/messages")

        assert resp.status_code == 200

    def test_returns_list_of_messages(self):
        history = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "2+2 equals 4."},
        ]
        svc = _make_conv_service(history=history)
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/conv-001/messages")

        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_messages_have_role_and_content(self):
        history = [{"role": "user", "content": "hi"}]
        svc = _make_conv_service(history=history)
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/conv-001/messages")

        msg = resp.json()[0]
        assert "role" in msg
        assert "content" in msg

    def test_messages_contain_correct_content(self):
        history = [
            {"role": "user", "content": "unique-user-message-text"},
            {"role": "assistant", "content": "unique-assistant-reply-text"},
        ]
        svc = _make_conv_service(history=history)
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/conv-001/messages")

        body = resp.json()
        assert body[0]["content"] == "unique-user-message-text"
        assert body[1]["content"] == "unique-assistant-reply-text"

    def test_messages_are_in_chronological_order(self):
        """Oldest message first — matches what ConversationService.load_history returns."""
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        svc = _make_conv_service(history=history)
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/conv-001/messages")

        data = resp.json()
        assert data[0]["content"] == "first"
        assert data[2]["content"] == "third"


class TestConversationsEndpointEmptyHistory:
    def test_returns_200_with_empty_list_for_new_conversation(self):
        """New conversation with no messages → 200 + [] (not 404)."""
        svc = _make_conv_service(history=[])
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/brand-new-conv/messages")

        assert resp.status_code == 200
        assert resp.json() == []


class TestConversationsEndpointNotFound:
    def test_returns_404_when_conversation_does_not_exist(self):
        """conversation_id not in DB → 404."""
        svc = AsyncMock()
        svc.load_history = AsyncMock(side_effect=Exception("conversation not found"))
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/nonexistent-id/messages")

        assert resp.status_code == 404

    def test_404_response_has_detail_field(self):
        svc = AsyncMock()
        svc.load_history = AsyncMock(side_effect=Exception("conversation not found"))
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            resp = client.get("/conversations/nonexistent-id/messages")

        assert "detail" in resp.json()


class TestConversationsEndpointConvIdInPath:
    def test_conversation_id_taken_from_path(self):
        """The conv id in the URL must be passed through to ConversationService."""
        svc = _make_conv_service(history=[])
        with patch("main.ConversationService", return_value=svc), \
             patch("main.get_db_service"):
            client = TestClient(app)
            client.get("/conversations/specific-conv-id-xyz/messages")

        svc.load_history.assert_called_once_with("specific-conv-id-xyz")
