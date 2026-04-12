"""initial_schema

Full CRUZ AI System schema.
Includes trace_id (request tracing), device (cross-device sync),
and tokens_used (cost tracking) from day one.

Revision ID: 0001
Revises:
Create Date: 2026-04-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255)),
        sa.Column(
            "created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False
        ),
    )

    # ------------------------------------------------------------------
    # conversations  (trace_id + device added from day one)
    # ------------------------------------------------------------------
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column(
            "trace_id",
            sa.String(64),
            nullable=True,
            comment="First trace_id that opened this conversation",
        ),
        sa.Column(
            "device",
            sa.String(50),
            nullable=True,
            comment="Originating device: mac_mini | ipad | phone | web",
        ),
        sa.Column("context", sa.JSON),
        sa.Column(
            "created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False
        ),
    )

    # ------------------------------------------------------------------
    # messages
    # ------------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.JSON),
        sa.Column(
            "created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False
        ),
    )

    # ------------------------------------------------------------------
    # tasks
    # ------------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("priority", sa.Integer, server_default="3"),
        sa.Column("metadata", sa.JSON),
        sa.Column(
            "created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False
        ),
        sa.Column("completed_at", sa.TIMESTAMP, nullable=True),
    )

    # ------------------------------------------------------------------
    # agent_logs  (trace_id + tokens_used added from day one)
    # ------------------------------------------------------------------
    op.create_table(
        "agent_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20)),
        sa.Column(
            "trace_id",
            sa.String(64),
            nullable=True,
            comment="Links every log row for a single user request",
        ),
        sa.Column(
            "tokens_used",
            sa.Integer,
            server_default="0",
            nullable=False,
            comment="Total LLM tokens (input + output) for this log entry",
        ),
        sa.Column("input_data", sa.JSON),
        sa.Column("output_data", sa.JSON),
        sa.Column("duration_ms", sa.Integer),
        sa.Column(
            "created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False
        ),
    )

    # ------------------------------------------------------------------
    # Indexes
    # ------------------------------------------------------------------
    op.create_index("idx_tasks_agent", "tasks", ["agent"])
    op.create_index("idx_tasks_status", "tasks", ["status"])
    op.create_index("idx_agent_logs_agent", "agent_logs", ["agent"])
    op.create_index("idx_agent_logs_trace_id", "agent_logs", ["trace_id"])
    op.create_index("idx_messages_conversation", "messages", ["conversation_id"])
    op.create_index("idx_conversations_trace_id", "conversations", ["trace_id"])


def downgrade() -> None:
    op.drop_index("idx_conversations_trace_id")
    op.drop_index("idx_messages_conversation")
    op.drop_index("idx_agent_logs_trace_id")
    op.drop_index("idx_agent_logs_agent")
    op.drop_index("idx_tasks_status")
    op.drop_index("idx_tasks_agent")

    op.drop_table("agent_logs")
    op.drop_table("tasks")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
