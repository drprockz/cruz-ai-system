"""
Real-PostgreSQL integration test (R6).

Unlike the other 796 tests which mock `get_db_service`, this suite talks
to an actual PostgreSQL. It catches schema/SQL drift that mocked tests
can't — e.g. "conversations.id is INTEGER but code passes UUID strings."

Opt-in: set DATABASE_URL_TEST to a throwaway DB URL. Example:
    export DATABASE_URL_TEST=postgresql://cruz:cruz_dev_password@localhost:5432/cruz_test_db

All tests are skipped when DATABASE_URL_TEST is unset. This keeps the
default `pytest` command from requiring any external service while still
making it possible to verify schema correctness locally and in CI.

What we verify:
  - Alembic migrations apply cleanly from scratch (via `alembic upgrade head`)
  - conversations.id accepts UUID strings (migration 0002 applied correctly)
  - messages FK conversation_id accepts UUID strings
  - ConversationService SQL round-trips (insert + load_history)
  - BaseAgent.log SQL writes trace_id + tokens_used successfully
"""

from __future__ import annotations

import os
import subprocess
import uuid
from typing import AsyncGenerator

import asyncpg
import pytest
import pytest_asyncio

_TEST_URL = os.environ.get("DATABASE_URL_TEST")
_SKIP_REASON = "DATABASE_URL_TEST not set — real-DB integration tests skipped"

pytestmark = pytest.mark.skipif(_TEST_URL is None, reason=_SKIP_REASON)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def migrated_db() -> AsyncGenerator[str, None]:
    """
    Drop the public schema, re-run all Alembic migrations from scratch,
    yield the test DB URL, then leave the schema in place for inspection.
    """
    assert _TEST_URL, "guarded by pytestmark.skipif"

    conn = await asyncpg.connect(_TEST_URL)
    try:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = _TEST_URL  # alembic env reads DATABASE_URL
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), "../.."),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic upgrade failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    yield _TEST_URL


@pytest_asyncio.fixture
async def conn(migrated_db: str) -> AsyncGenerator[asyncpg.Connection, None]:
    conn = await asyncpg.connect(migrated_db)
    try:
        # Clean row data between tests (schema stays)
        await conn.execute("TRUNCATE agent_logs, messages, conversations, tasks RESTART IDENTITY CASCADE")
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Schema existence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSchemaShape:
    async def test_all_expected_tables_exist(self, conn: asyncpg.Connection):
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        names = {r["table_name"] for r in rows}
        for expected in ("users", "conversations", "messages", "tasks", "agent_logs"):
            assert expected in names, f"missing table: {expected}"

    async def test_conversations_id_is_string(self, conn: asyncpg.Connection):
        """Migration 0002 must have converted conversations.id to VARCHAR."""
        row = await conn.fetchrow(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='conversations' AND column_name='id'"
        )
        assert row["data_type"] == "character varying"

    async def test_messages_conversation_id_is_string(self, conn: asyncpg.Connection):
        """FK type must match conversations.id — otherwise inserts fail."""
        row = await conn.fetchrow(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='messages' AND column_name='conversation_id'"
        )
        assert row["data_type"] == "character varying"

    async def test_agent_logs_has_trace_id_and_tokens_used(self, conn: asyncpg.Connection):
        """BaseAgent.log() writes these columns — they must exist."""
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='agent_logs'"
        )
        cols = {r["column_name"] for r in rows}
        assert "trace_id" in cols
        assert "tokens_used" in cols

    async def test_users_has_preferences_column(self, conn: asyncpg.Connection):
        """Procedural memory needs users.preferences JSONB."""
        row = await conn.fetchrow(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='preferences'"
        )
        assert row is not None, "users.preferences column missing"


# ---------------------------------------------------------------------------
# ConversationService SQL round-trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestConversationRoundTrip:
    async def test_insert_conversation_with_uuid_id(self, conn: asyncpg.Connection):
        conv_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO conversations (id) VALUES ($1)",
            conv_id,
        )
        row = await conn.fetchrow(
            "SELECT id FROM conversations WHERE id = $1",
            conv_id,
        )
        assert row["id"] == conv_id

    async def test_insert_message_with_uuid_fk(self, conn: asyncpg.Connection):
        conv_id = str(uuid.uuid4())
        await conn.execute("INSERT INTO conversations (id) VALUES ($1)", conv_id)
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'user', $2)",
            conv_id,
            "hello cruz",
        )
        msg = await conn.fetchrow(
            "SELECT role, content FROM messages WHERE conversation_id = $1",
            conv_id,
        )
        assert msg["role"] == "user"
        assert msg["content"] == "hello cruz"

    async def test_load_history_returns_chronological_messages(self, conn: asyncpg.Connection):
        """Replicates ConversationService.load_history SQL exactly."""
        conv_id = str(uuid.uuid4())
        await conn.execute("INSERT INTO conversations (id) VALUES ($1)", conv_id)
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'user', 'first')",
            conv_id,
        )
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'assistant', 'second')",
            conv_id,
        )
        rows = await conn.fetch(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            LIMIT 50
            """,
            conv_id,
        )
        assert [r["role"] for r in rows] == ["user", "assistant"]
        assert [r["content"] for r in rows] == ["first", "second"]


# ---------------------------------------------------------------------------
# BaseAgent.log SQL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAgentLogsRoundTrip:
    async def test_base_agent_log_sql_runs(self, conn: asyncpg.Connection):
        """Exercise exactly the INSERT that BaseAgent.log emits."""
        trace_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO agent_logs
                (trace_id, agent, action, status, input_data, output_data,
                 tokens_used, duration_ms)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
            """,
            trace_id,
            "FORGE",
            "process",
            "success",
            '{"task": "write tests"}',
            '{"result": "done"}',
            1234,
            87,
        )
        row = await conn.fetchrow(
            "SELECT agent, status, tokens_used FROM agent_logs WHERE trace_id = $1",
            trace_id,
        )
        assert row["agent"] == "FORGE"
        assert row["status"] == "success"
        assert row["tokens_used"] == 1234
