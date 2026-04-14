"""
Tests for lifespan monitoring init:
  - Sentry SDK initialised if SENTRY_DSN set
  - Loki handler attached if LOKI_URL set
  - Both skipped silently when env vars absent
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sentry_initialised_when_dsn_set(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://abc@sentry.io/1")
    mock_sentry = MagicMock()
    import sys
    sys.modules["sentry_sdk"] = mock_sentry
    with patch("backend.api.main._validate_required_env"), \
         patch("backend.api.main.get_db_service") as db, \
         patch("backend.api.main.get_redis_service") as rs, \
         patch("backend.api.main.get_qdrant_service") as qs:
        db.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        rs.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        qs.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        from backend.api.main import lifespan, app
        async with lifespan(app):
            pass
    mock_sentry.init.assert_called_once()
    kwargs = mock_sentry.init.call_args.kwargs
    assert kwargs.get("dsn") == "https://abc@sentry.io/1"


@pytest.mark.asyncio
async def test_sentry_skipped_when_dsn_absent(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    mock_sentry = MagicMock()
    import sys
    sys.modules["sentry_sdk"] = mock_sentry
    with patch("backend.api.main._validate_required_env"), \
         patch("backend.api.main.get_db_service") as db, \
         patch("backend.api.main.get_redis_service") as rs, \
         patch("backend.api.main.get_qdrant_service") as qs:
        db.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        rs.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        qs.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        from backend.api.main import lifespan, app
        async with lifespan(app):
            pass
    mock_sentry.init.assert_not_called()


@pytest.mark.asyncio
async def test_loki_handler_installed_when_url_set(monkeypatch):
    monkeypatch.setenv("LOKI_URL", "http://localhost:3100")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    with patch("backend.api.main._validate_required_env"), \
         patch("backend.api.main.get_db_service") as db, \
         patch("backend.api.main.get_redis_service") as rs, \
         patch("backend.api.main.get_qdrant_service") as qs, \
         patch("backend.api.main.install_loki_logging") as ill:
        db.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        rs.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        qs.return_value = MagicMock(connect=AsyncMock(), disconnect=AsyncMock())
        from backend.api.main import lifespan, app
        async with lifespan(app):
            pass
    ill.assert_called_once()
