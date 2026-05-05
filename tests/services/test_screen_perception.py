"""Unit tests for services.screen_perception — subprocess + LLM mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.mac_controller import MacControllerError
from services.screen_perception import (
    ActiveWindow,
    ScreenAnalysis,
    ScreenPerceptionError,
    ScreenPerceptionService,
    WINDOW_TITLE_ALLOWLIST,
    get_screen_perception_service,
)


def test_singleton_returns_same_instance() -> None:
    a = get_screen_perception_service()
    b = get_screen_perception_service()
    assert a is b
    assert isinstance(a, ScreenPerceptionService)


def test_screen_perception_error_is_runtime_error() -> None:
    err = ScreenPerceptionError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"


def test_window_title_allowlist_contains_dev_tools() -> None:
    """Sanity: the allowlist is the set the spec §4 defines, no extras."""
    expected = {
        "Code", "Cursor", "Xcode", "Terminal", "iTerm2",
        "PyCharm", "WebStorm", "Sublime Text", "Zed", "Ghostty",
    }
    assert WINDOW_TITLE_ALLOWLIST == expected


def test_active_window_to_context_line_app_only() -> None:
    aw = ActiveWindow(app="Mail", window_title=None, captured_at=0.0)
    assert aw.to_context_line() == "- Active app: Mail"


def test_active_window_to_context_line_with_title() -> None:
    aw = ActiveWindow(
        app="Code",
        window_title="orders.js — ama-solutions",
        captured_at=0.0,
    )
    assert aw.to_context_line() == "- Active app: Code — orders.js — ama-solutions"


def test_screen_analysis_dataclass_fields() -> None:
    """Confirm the dataclass shape the dispatch path depends on."""
    aw = ActiveWindow(app="Code", window_title="x", captured_at=1.0)
    sa = ScreenAnalysis(
        answer="hello",
        active_window=aw,
        image_bytes_len=42,
        duration_ms=100,
        tokens_used=200,
    )
    assert sa.answer == "hello"
    assert sa.active_window is aw
    assert sa.image_bytes_len == 42
    assert sa.duration_ms == 100
    assert sa.tokens_used == 200


@pytest.mark.asyncio
async def test_get_active_window_app_only_non_allowlisted() -> None:
    """Non-allowlisted app: only app name is captured, no window title."""
    svc = ScreenPerceptionService()
    # Patch the helper that runs osascript so step-1 returns "Mail".
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Mail"),
    ) as step1, patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value=""),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Mail"
    assert aw.window_title is None
    step1.assert_awaited_once()
    # Step-2 must NOT be called for non-allowlisted apps.
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_with_title_allowlisted() -> None:
    """Allowlisted app: window title captured."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="orders.js — ama-solutions"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Code"
    assert aw.window_title == "orders.js — ama-solutions"
    step2.assert_awaited_once_with("Code")


@pytest.mark.asyncio
async def test_get_active_window_blocks_title_for_non_allowlisted() -> None:
    """Safari is NOT in the allowlist — step-2 must not be called."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Safari"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="should-not-appear"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "Safari"
    assert aw.window_title is None
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_allowlist_is_case_sensitive() -> None:
    """Lowercase 'code' (vs allowlisted 'Code') falls through to app-only."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value="should-not-appear"),
    ) as step2:
        aw = await svc.get_active_window()
    assert aw.app == "code"
    assert aw.window_title is None
    step2.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_window_step1_failure_returns_unknown() -> None:
    """Step-1 raising → returns ActiveWindow(app='unknown', ...); never raises."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(side_effect=MacControllerError("osascript not found")),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "unknown"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step1_empty_returns_unknown() -> None:
    """Step-1 returning '' → ActiveWindow(app='unknown', ...)."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value=""),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "unknown"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step2_failure_returns_app_only() -> None:
    """Step-2 raising → app preserved, window_title=None."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Code"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(side_effect=MacControllerError("window not found")),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "Code"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_step2_empty_string_becomes_none() -> None:
    """Step-2 returning '' (no front window) → window_title=None, not ''."""
    svc = ScreenPerceptionService()
    with patch.object(
        svc, "_run_osascript_for_step1",
        new=AsyncMock(return_value="Terminal"),
    ), patch.object(
        svc, "_run_osascript_for_step2",
        new=AsyncMock(return_value=""),
    ):
        aw = await svc.get_active_window()
    assert aw.app == "Terminal"
    assert aw.window_title is None


@pytest.mark.asyncio
async def test_get_active_window_app_name_regex_rejects_injection() -> None:
    """If step-1 somehow returns a string that fails APP_NAME_RE,
    step-2 must not be called even if the name is in the allowlist."""
    svc = ScreenPerceptionService()
    # Construct a string that isn't in the allowlist by exact match
    # but would also fail the regex. Tests defense-in-depth: allowlist
    # is the primary block, regex is the secondary one for any future
    # allowlist entry that contains unsafe characters.
    # We monkeypatch the allowlist to include the malicious string so
    # we exercise the regex check specifically.
    import services.screen_perception as sp_mod
    original = sp_mod.WINDOW_TITLE_ALLOWLIST
    sp_mod.WINDOW_TITLE_ALLOWLIST = frozenset({'Bad"; rm -rf /'})
    try:
        with patch.object(
            svc, "_run_osascript_for_step1",
            new=AsyncMock(return_value='Bad"; rm -rf /'),
        ), patch.object(
            svc, "_run_osascript_for_step2",
            new=AsyncMock(return_value="should-not-appear"),
        ) as step2:
            aw = await svc.get_active_window()
        assert aw.app == 'Bad"; rm -rf /'
        assert aw.window_title is None
        step2.assert_not_called()
    finally:
        sp_mod.WINDOW_TITLE_ALLOWLIST = original


@pytest.mark.asyncio
async def test_analyze_happy_path() -> None:
    """analyze() returns a ScreenAnalysis with sanitized answer + window metadata."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()

    # Mock mac_controller.screenshot
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

    # Mock active window
    aw_fixed = ActiveWindow(app="Code", window_title="hello.py", captured_at=1.0)

    # Mock LLM response — duck-typed shape from anthropic_chat.
    # Use a deliberately bland string that no current OR foreseeable
    # privacy_engine regex can match (no URLs, no credentials, no
    # accounts, no key prefixes, no digit runs). This decouples the
    # happy-path assertion from sanitize evolution; the dedicated
    # test_analyze_sanitizes_output below exercises sanitize behavior.
    bland_answer = "User is editing code."
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=bland_answer)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )

    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw_fixed),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=fake_png)
        result = await svc.analyze()

    assert isinstance(result, ScreenAnalysis)
    assert result.answer == bland_answer
    assert result.active_window is aw_fixed
    assert result.image_bytes_len == len(fake_png)
    assert result.tokens_used == 120
    assert result.duration_ms >= 0

    # Verify llm.chat was called with anthropic backend + sonnet model
    call = mock_llm.await_args
    assert call.kwargs["backend"] == "anthropic"
    assert call.kwargs["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_analyze_screenshot_failure_raises() -> None:
    """mac.screenshot raising MacControllerError → ScreenPerceptionError."""
    svc = ScreenPerceptionService()
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac:
        mock_mac.return_value.screenshot = AsyncMock(
            side_effect=MacControllerError("screencapture: error 1")
        )
        with pytest.raises(ScreenPerceptionError, match="screenshot failed"):
            await svc.analyze()


@pytest.mark.asyncio
async def test_analyze_vision_failure_raises() -> None:
    """llm.chat raising → ScreenPerceptionError('vision call failed: ...')."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(side_effect=RuntimeError("anthropic: 503")),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        with pytest.raises(ScreenPerceptionError, match="vision call failed"):
            await svc.analyze()


@pytest.mark.asyncio
async def test_analyze_default_question_uses_canonical_prompt() -> None:
    """When question=None, the canonical prompt template is used."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        await svc.analyze()
    msgs = mock_llm.await_args.kwargs["messages"]
    text_block = next(b for b in msgs[0]["content"] if b["type"] == "text")
    assert "currently working on" in text_block["text"].lower()


@pytest.mark.asyncio
async def test_analyze_custom_question_passed_through() -> None:
    """Custom question appears verbatim in the Vision prompt."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        await svc.analyze(question="What error is shown in the terminal?")
    msgs = mock_llm.await_args.kwargs["messages"]
    text_block = next(b for b in msgs[0]["content"] if b["type"] == "text")
    assert text_block["text"] == "What error is shown in the terminal?"


@pytest.mark.asyncio
async def test_analyze_image_content_block_shape() -> None:
    """Image content block: type=image, source.type=base64,
    media_type=image/png, data is STANDARD base64 (not URL-safe)."""
    import base64 as _b64
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    # Use bytes that produce '+' or '/' in standard base64 (so URL-safe
    # variant would have '-' or '_' instead — assertable difference).
    png = bytes(range(256))
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ) as mock_llm:
        mock_mac.return_value.screenshot = AsyncMock(return_value=png)
        await svc.analyze()
    msgs = mock_llm.await_args.kwargs["messages"]
    image_block = msgs[0]["content"][0]
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    data = image_block["source"]["data"]
    # Standard base64 alphabet uses '+' and '/'. URL-safe uses '-' and '_'.
    assert "_" not in data and "-" not in data
    # Round-trip: standard_b64decode must equal the original bytes.
    assert _b64.standard_b64decode(data) == png


@pytest.mark.asyncio
async def test_analyze_sanitizes_output() -> None:
    """Vision answer containing a URL password is sanitized in result.answer."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    leaky = "Connection: postgres://user:topsecret@db/cruz"
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=leaky)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        result = await svc.analyze()
    assert "topsecret" not in result.answer
    assert "[REDACTED_PW]" in result.answer


@pytest.mark.asyncio
async def test_analyze_empty_text_response_returns_empty_string() -> None:
    """If Vision returns no text block (refusal / weird), answer is ''
    and the call still succeeds (caller decides what to do)."""
    from types import SimpleNamespace
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[],   # no text blocks
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=0),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        result = await svc.analyze()
    assert result.answer == ""


@pytest.mark.asyncio
async def test_analyze_sanitize_failure_falls_through_to_raw_text(caplog) -> None:
    """If sanitize raises, the call still succeeds and answer = raw text;
    a warning is logged. Verifies the privacy-degraded-mode fallback."""
    from types import SimpleNamespace
    import logging
    svc = ScreenPerceptionService()
    aw = ActiveWindow(app="X", window_title=None, captured_at=0.0)
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="raw vision answer")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch(
        "services.screen_perception.get_mac_controller_service",
    ) as mock_mac, patch.object(
        svc, "get_active_window",
        new=AsyncMock(return_value=aw),
    ), patch(
        "services.screen_perception.llm_chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "agents.cruz.persona.privacy_engine.sanitize",
        side_effect=RuntimeError("regex compile failed"),
    ):
        mock_mac.return_value.screenshot = AsyncMock(return_value=b"\x89PNG")
        with caplog.at_level(logging.WARNING, logger="cruz.services.screen_perception"):
            result = await svc.analyze()
    assert result.answer == "raw vision answer"   # raw text, NOT sanitized
    # A warning was logged about the sanitize failure
    assert any("sanitize" in record.message.lower() for record in caplog.records)
