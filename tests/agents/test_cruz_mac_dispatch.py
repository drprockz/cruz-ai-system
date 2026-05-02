"""Verify CruzAgent._dispatch_tool routes mac_* tools to MacControllerService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.cruz.cruz_agent import CruzAgent


@pytest.mark.asyncio
async def test_dispatch_mac_screenshot_returns_png_meta() -> None:
    cruz = CruzAgent()
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with patch(
        "agents.cruz.cruz_agent.get_mac_controller_service"
    ) as mock_get:
        mock_get.return_value.screenshot = AsyncMock(return_value=fake_png)
        out = await cruz._dispatch_tool(
            tool_name="mac_screenshot",
            tool_input={},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    assert out["result"]["bytes_len"] == len(fake_png)
    assert out["result"]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_dispatch_mac_clipboard_read() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.clipboard_read = AsyncMock(return_value="hello")
        out = await cruz._dispatch_tool(
            tool_name="mac_clipboard_read",
            tool_input={},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    assert out["result"] == "hello"


@pytest.mark.asyncio
async def test_dispatch_mac_clipboard_write() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.clipboard_write = AsyncMock(return_value=None)
        out = await cruz._dispatch_tool(
            tool_name="mac_clipboard_write",
            tool_input={"text": "paste me"},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    mock_get.return_value.clipboard_write.assert_awaited_once_with("paste me")


@pytest.mark.asyncio
async def test_dispatch_mac_open_app() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.open_app = AsyncMock(return_value=None)
        out = await cruz._dispatch_tool(
            tool_name="mac_open_app",
            tool_input={"name": "TextEdit"},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    mock_get.return_value.open_app.assert_awaited_once_with("TextEdit")


@pytest.mark.asyncio
async def test_dispatch_mac_notify() -> None:
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.notify = AsyncMock(return_value=None)
        out = await cruz._dispatch_tool(
            tool_name="mac_notify",
            tool_input={"title": "Hi", "body": "Body", "sound": True},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is True
    mock_get.return_value.notify.assert_awaited_once_with("Hi", "Body", sound=True)


@pytest.mark.asyncio
async def test_dispatch_mac_tool_error_returns_failure() -> None:
    from services.mac_controller import MacControllerError
    cruz = CruzAgent()
    with patch("agents.cruz.cruz_agent.get_mac_controller_service") as mock_get:
        mock_get.return_value.notify = AsyncMock(
            side_effect=MacControllerError("permission denied")
        )
        out = await cruz._dispatch_tool(
            tool_name="mac_notify",
            tool_input={"title": "x", "body": "y"},
            trace_id="t1",
            conversation_id="c1",
        )
    assert out["success"] is False
    assert "permission denied" in out["error"]
