"""Unit tests for the Gmail client helpers — focus on _fetch_thread_replied_sync,
since the followup agent only mocks the public coroutine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.reply_triage.gmail_client import _fetch_thread_replied_sync


def _fake_service(messages: list[dict]) -> MagicMock:
    """Build a stand-in for the googleapiclient discovery resource that
    returns the supplied messages from threads().get().execute()."""
    svc = MagicMock()
    execute_mock = MagicMock(return_value={"messages": messages})
    get_mock = MagicMock(return_value=MagicMock(execute=execute_mock))
    threads_mock = MagicMock(return_value=MagicMock(get=get_mock))
    users_mock = MagicMock(return_value=MagicMock(threads=threads_mock))
    svc.users = users_mock
    return svc


@pytest.mark.parametrize(
    "messages,expected,description",
    [
        # No messages at all → not replied.
        ([], False, "empty thread"),
        # Only inbound messages (we never sent) → not replied (nothing to chase).
        (
            [{"internalDate": "1000", "labelIds": ["INBOX"]}],
            False,
            "inbound-only, we never sent",
        ),
        # We sent and the client never responded → not replied.
        (
            [{"internalDate": "1000", "labelIds": ["SENT"]}],
            False,
            "we sent, no inbound after",
        ),
        # Client sent first, we replied; no further client message → not replied
        # (our SENT is the latest message; the client owes a reply, but our
        # FollowupAgent only chases the case where WE sent and the client owes).
        (
            [
                {"internalDate": "1000", "labelIds": ["INBOX"]},
                {"internalDate": "2000", "labelIds": ["SENT"]},
            ],
            False,
            "client first, we replied last",
        ),
        # We sent, client replied → REPLIED (drop from followup queue).
        (
            [
                {"internalDate": "1000", "labelIds": ["SENT"]},
                {"internalDate": "2000", "labelIds": ["INBOX"]},
            ],
            True,
            "we sent, client replied",
        ),
        # Full back-and-forth ending with us → not replied (we sent last).
        (
            [
                {"internalDate": "1000", "labelIds": ["SENT"]},
                {"internalDate": "2000", "labelIds": ["INBOX"]},
                {"internalDate": "3000", "labelIds": ["SENT"]},
            ],
            False,
            "back-and-forth ending with us",
        ),
        # Full back-and-forth ending with client → REPLIED.
        (
            [
                {"internalDate": "1000", "labelIds": ["SENT"]},
                {"internalDate": "2000", "labelIds": ["INBOX"]},
                {"internalDate": "3000", "labelIds": ["SENT"]},
                {"internalDate": "4000", "labelIds": ["INBOX"]},
            ],
            True,
            "back-and-forth ending with client",
        ),
        # Out-of-order internalDate — must sort before evaluating.
        (
            [
                {"internalDate": "2000", "labelIds": ["INBOX"]},
                {"internalDate": "1000", "labelIds": ["SENT"]},
            ],
            True,
            "out-of-order; sort by internalDate first",
        ),
    ],
)
def test_fetch_thread_replied_classifies_correctly(messages, expected, description):
    fake_svc = _fake_service(messages)
    with patch("agents.reply_triage.gmail_client._get_service",
               return_value=fake_svc):
        assert _fetch_thread_replied_sync("any-thread-id") is expected, description


def test_fetch_thread_replied_returns_false_on_api_exception():
    svc = MagicMock()
    execute_mock = MagicMock(side_effect=Exception("boom"))
    get_mock = MagicMock(return_value=MagicMock(execute=execute_mock))
    threads_mock = MagicMock(return_value=MagicMock(get=get_mock))
    users_mock = MagicMock(return_value=MagicMock(threads=threads_mock))
    svc.users = users_mock
    with patch("agents.reply_triage.gmail_client._get_service",
               return_value=svc):
        assert _fetch_thread_replied_sync("t1") is False
