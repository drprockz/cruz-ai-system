"""agent_state

Add agent_state table for SP5 event-driven per-agent persistent state.

Spec:    docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §3.1
Charter override: Rule 5 (no new tables) — see spec §11.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_state",
        sa.Column("agent_name", sa.String(50),    nullable=False),
        sa.Column("key",        sa.String(200),   nullable=False),
        sa.Column("value",      postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP,     nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP,
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("agent_name", "key"),
    )
    # Partial index — only rows with expires_at need fast cleanup scans.
    op.execute(
        "CREATE INDEX idx_agent_state_expires "
        "ON agent_state(expires_at) WHERE expires_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_state_expires")
    op.drop_table("agent_state")
