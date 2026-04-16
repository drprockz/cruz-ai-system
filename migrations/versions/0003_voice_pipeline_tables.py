"""voice_pipeline_tables

Adds the tables needed by the Phase 1 voice pipeline:
  - voice_sessions: one row per LiveKit voice session (cruz__<conv>__<device>)
  - approval_requests: destructive-action approvals surfaced via FCM push
  - fcm_tokens: registered device tokens for push notifications

Also adds two columns on messages:
  - voice_session_id: FK linking a message to its voice session
  - audio_ms: length of the spoken turn in milliseconds

Spec: docs/superpowers/specs/2026-04-15-voice-pipeline-v2.md §6

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── voice_sessions ────────────────────────────────────────────────
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("device_id", sa.String(100), nullable=False),
        sa.Column("livekit_room", sa.String(200), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.TIMESTAMP, nullable=True),
        sa.Column(
            "deepgram_ws_ms", sa.Integer, server_default=sa.text("0"), nullable=False
        ),
        sa.Column("turns", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("barges", sa.Integer, server_default=sa.text("0"), nullable=False),
    )
    op.create_index(
        "idx_voice_sessions_conv", "voice_sessions", ["conversation_id"]
    )

    # ── approval_requests ─────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "state", sa.String(20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.TIMESTAMP, nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP, nullable=False),
    )
    op.create_index(
        "idx_approval_requests_trace", "approval_requests", ["trace_id"]
    )
    op.create_index(
        "idx_approval_requests_state",
        "approval_requests",
        ["state", "expires_at"],
    )

    # ── fcm_tokens ────────────────────────────────────────────────────
    op.create_table(
        "fcm_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("device", sa.String(50), nullable=False),
        sa.Column("token", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "device", name="uq_fcm_tokens_user_device"),
    )

    # ── messages: voice_session_id + audio_ms ─────────────────────────
    op.add_column(
        "messages",
        sa.Column(
            "voice_session_id",
            sa.String(36),
            sa.ForeignKey("voice_sessions.id"),
            nullable=True,
        ),
    )
    op.add_column("messages", sa.Column("audio_ms", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "audio_ms")
    op.drop_column("messages", "voice_session_id")

    op.drop_table("fcm_tokens")

    op.drop_index("idx_approval_requests_state", table_name="approval_requests")
    op.drop_index("idx_approval_requests_trace", table_name="approval_requests")
    op.drop_table("approval_requests")

    op.drop_index("idx_voice_sessions_conv", table_name="voice_sessions")
    op.drop_table("voice_sessions")
