"""
Tests for startup env-var validation (R3).

At process startup, the server must fail fast with a clear message if any
required environment variable is missing. Deferring to the first agent
call leaves operators debugging "why is CRUZ silent at 3 AM" instead.

Required at startup:
  - ANTHROPIC_API_KEY  (every Claude-based agent)
  - DATABASE_URL       (PostgreSQL pool)
  - REDIS_URL          (Redis + device handoff)
  - QDRANT_URL         (semantic memory)

Optional (warn but don't block):
  - GEMINI_API_KEY, GITHUB_TOKEN, INWORLD_API_KEY, NOTION_API_KEY, etc.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/api"))


class TestValidateRequiredEnv:
    def test_validate_required_env_is_importable(self):
        from main import _validate_required_env  # noqa: F401

    def test_passes_when_all_required_set(self):
        from main import _validate_required_env
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "DATABASE_URL": "postgresql://u:p@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "QDRANT_URL": "http://localhost:6333",
        }
        with patch.dict(os.environ, env, clear=False):
            # Should not raise
            _validate_required_env()

    def test_raises_when_anthropic_key_missing(self):
        from main import _validate_required_env
        env = {
            "DATABASE_URL": "postgresql://u:p@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "QDRANT_URL": "http://localhost:6333",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                _validate_required_env()

    def test_raises_when_database_url_missing(self):
        from main import _validate_required_env
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "REDIS_URL": "redis://localhost:6379",
            "QDRANT_URL": "http://localhost:6333",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                _validate_required_env()

    def test_raises_when_redis_url_missing(self):
        from main import _validate_required_env
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "DATABASE_URL": "postgresql://u:p@localhost/db",
            "QDRANT_URL": "http://localhost:6333",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="REDIS_URL"):
                _validate_required_env()

    def test_raises_when_qdrant_url_missing(self):
        from main import _validate_required_env
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "DATABASE_URL": "postgresql://u:p@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="QDRANT_URL"):
                _validate_required_env()

    def test_error_lists_all_missing_vars(self):
        """Error message names every missing var, not just the first one."""
        from main import _validate_required_env
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                _validate_required_env()
        msg = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in msg
        assert "DATABASE_URL" in msg
        assert "REDIS_URL" in msg
        assert "QDRANT_URL" in msg

    def test_empty_string_treated_as_missing(self):
        """Empty values count as missing (operator forgot to fill .env.example)."""
        from main import _validate_required_env
        env = {
            "ANTHROPIC_API_KEY": "",
            "DATABASE_URL": "postgresql://u:p@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "QDRANT_URL": "http://localhost:6333",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                _validate_required_env()
