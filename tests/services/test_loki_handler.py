"""
Tests for LokiHandler — logging.Handler that pushes structured logs to
a Grafana Loki instance via its /loki/api/v1/push endpoint.

Contract:
  h = LokiHandler(url="http://localhost:3100", labels={"app": "cruz"})
  logger.addHandler(h); logger.info("hello")
  → fire-and-forget POST; failure never raises.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


def _mock_resp(status: int = 204):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "ok" if status < 300 else "bad"
    return resp


class TestLokiHandlerInterface:
    def test_can_be_imported(self):
        from services.alerts import LokiHandler  # noqa

    def test_is_logging_handler(self):
        from services.alerts import LokiHandler
        assert issubclass(LokiHandler, logging.Handler)


class TestLokiHandlerEmit:
    def test_posts_log_to_loki(self):
        from services.alerts import LokiHandler
        with patch("services.alerts.httpx.post", return_value=_mock_resp(204)) as post:
            h = LokiHandler(url="http://localhost:3100", labels={"app": "cruz"})
            record = logging.LogRecord(
                name="cruz.test", level=logging.INFO, pathname="t.py",
                lineno=1, msg="hello %s", args=("world",), exc_info=None,
            )
            h.emit(record)
        post.assert_called_once()
        url = post.call_args.args[0]
        assert url.endswith("/loki/api/v1/push")
        body = post.call_args.kwargs["json"]
        stream = body["streams"][0]
        assert stream["stream"]["app"] == "cruz"
        assert stream["stream"]["level"] == "info"
        # values is [[ns_ts, line], ...]
        ts, line = stream["values"][0]
        assert ts.isdigit() and len(ts) >= 16  # nanoseconds
        assert "hello world" in line

    def test_emit_swallows_errors(self):
        from services.alerts import LokiHandler
        with patch("services.alerts.httpx.post", side_effect=RuntimeError("down")):
            h = LokiHandler(url="http://localhost:3100")
            record = logging.LogRecord(
                name="x", level=logging.ERROR, pathname="t.py",
                lineno=1, msg="boom", args=None, exc_info=None,
            )
            h.emit(record)  # must not raise


class TestInstallLokiLogging:
    def test_installs_when_url_set(self, monkeypatch):
        from services.alerts import install_loki_logging, LokiHandler
        monkeypatch.setenv("LOKI_URL", "http://localhost:3100")
        root = logging.getLogger("cruz.loki.test1")
        root.handlers.clear()
        installed = install_loki_logging(logger=root)
        assert installed is True
        assert any(isinstance(h, LokiHandler) for h in root.handlers)

    def test_skips_when_url_missing(self, monkeypatch):
        from services.alerts import install_loki_logging, LokiHandler
        monkeypatch.delenv("LOKI_URL", raising=False)
        root = logging.getLogger("cruz.loki.test2")
        root.handlers.clear()
        installed = install_loki_logging(logger=root)
        assert installed is False
        assert not any(isinstance(h, LokiHandler) for h in root.handlers)
