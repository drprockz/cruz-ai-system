"""Unit tests for services.gcal — Google client mocked."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.gcal import (
    GCalAuthError,
    GCalError,
    GCalService,
    get_gcal_service,
)


# ── Singleton ─────────────────────────────────────────────────────────


def test_singleton(tmp_path, monkeypatch) -> None:
    import services.gcal as gcal_mod
    monkeypatch.setattr(gcal_mod, "_instance", None)
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    a = get_gcal_service()
    b = get_gcal_service()
    assert a is b


# ── Auth ──────────────────────────────────────────────────────────────


def test_load_credentials_missing_token_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(tmp_path / "missing.json"))
    svc = GCalService()
    with pytest.raises(GCalAuthError, match="token file not found"):
        svc._load_credentials()


def test_load_credentials_malformed_token_raises(tmp_path, monkeypatch) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{")
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(bad))
    svc = GCalService()
    with pytest.raises(GCalAuthError):
        svc._load_credentials()


# ── create_event ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_event_self_only(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("GCAL_DEFAULT_CALENDAR_ID", "primary")

    svc = GCalService()
    fake_event = {
        "id": "abc123",
        "htmlLink": "https://calendar.google.com/...",
        "summary": "Deep work",
    }
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = fake_event

    with patch.object(svc, "_build_service", return_value=mock_service):
        result = await svc.create_event(
            title="Deep work",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T12:00:00",
        )

    assert result["id"] == "abc123"
    body = mock_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["summary"] == "Deep work"
    assert body["start"]["dateTime"] == "2026-05-01T10:00:00"
    assert body["end"]["dateTime"] == "2026-05-01T12:00:00"
    assert "attendees" not in body  # self-only


@pytest.mark.asyncio
async def test_create_event_with_attendees(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = {"id": "x"}
    with patch.object(svc, "_build_service", return_value=mock_service):
        await svc.create_event(
            title="Sync",
            start_iso="2026-05-01T10:00:00",
            end_iso="2026-05-01T11:00:00",
            attendees=["a@x.com", "b@y.com"],
            description="agenda",
            location="Zoom",
        )
    body = mock_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["attendees"] == [{"email": "a@x.com"}, {"email": "b@y.com"}]
    assert body["description"] == "agenda"
    assert body["location"] == "Zoom"


@pytest.mark.asyncio
async def test_create_event_http_error_raises_gcal_error(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    from googleapiclient.errors import HttpError
    mock_service = MagicMock()
    err = HttpError(resp=MagicMock(status=500, reason="Server Error"), content=b"boom")
    mock_service.events.return_value.insert.return_value.execute.side_effect = err
    with patch.object(svc, "_build_service", return_value=mock_service):
        with pytest.raises(GCalError, match="500"):
            await svc.create_event(
                title="x",
                start_iso="2026-05-01T10:00:00",
                end_iso="2026-05-01T11:00:00",
            )


# ── list_events ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_events(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "e1", "summary": "A", "start": {"dateTime": "2026-05-01T10:00:00"}},
            {"id": "e2", "summary": "B", "start": {"dateTime": "2026-05-01T14:00:00"}},
        ],
    }
    with patch.object(svc, "_build_service", return_value=mock_service):
        events = await svc.list_events(
            start_iso="2026-05-01T00:00:00",
            end_iso="2026-05-02T00:00:00",
        )
    assert len(events) == 2
    assert events[0]["id"] == "e1"
    kwargs = mock_service.events.return_value.list.call_args.kwargs
    assert kwargs["timeMin"] == "2026-05-01T00:00:00Z"
    assert kwargs["timeMax"] == "2026-05-02T00:00:00Z"
    assert kwargs["singleEvents"] is True
    assert kwargs["orderBy"] == "startTime"


# ── delete_event ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_event(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(
        '{"refresh_token": "x", "client_id": "y", "client_secret": "z", '
        '"token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setenv("GCAL_TOKEN_PATH", str(token_path))
    svc = GCalService()
    mock_service = MagicMock()
    mock_service.events.return_value.delete.return_value.execute.return_value = ""
    with patch.object(svc, "_build_service", return_value=mock_service):
        await svc.delete_event("abc123")
    mock_service.events.return_value.delete.assert_called_once_with(
        calendarId="primary", eventId="abc123"
    )
