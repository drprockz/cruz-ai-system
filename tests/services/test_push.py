# tests/services/test_push.py
"""Unit tests for services/push — firebase-admin entirely mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.push import PushPayload, PushService, SendResult


class _FakeDB:
    """Stand-in for DatabaseService — captures executed queries for asserts."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []

    async def fetch(self, query, *params):
        self.executed.append(("fetch", query, params))
        return self.rows

    async def execute(self, query, *params):
        self.executed.append(("execute", query, params))


@pytest.fixture
def fake_db():
    return _FakeDB(rows=[{"fcm_token": "T1"}, {"fcm_token": "T2"}])


@pytest.fixture
def fake_messaging():
    """Patches firebase_admin.messaging globally; tests interact via this."""
    with patch("services.push.messaging") as m:
        # `messaging.send` is sync in firebase-admin; the service wraps it
        # in asyncio.to_thread.
        m.send.return_value = "msg_abc123"
        yield m


def test_push_payload_dataclass_fields():
    p = PushPayload(title="Hello", body="World")
    assert p.title == "Hello"
    assert p.body == "World"
    assert p.url is None
    assert p.trace_id is None


def test_push_service_construct_loads_credentials(monkeypatch, tmp_path):
    """The constructor must initialize a firebase app from the SA path."""
    sa_path = tmp_path / "sa.json"
    sa_path.write_text("{}")  # firebase-admin will be mocked, contents irrelevant
    with patch("services.push.credentials") as creds, \
         patch("services.push.initialize_app") as init_app:
        creds.Certificate.return_value = "fake-creds"
        svc = PushService(sa_path=str(sa_path), project_id="cruz-test")
    creds.Certificate.assert_called_once_with(str(sa_path))
    init_app.assert_called_once()
