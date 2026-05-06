"""projects_add_email_domains

Add email_domains TEXT[] column to projects table for Reply Triage
client_match resolution.

Spec: docs/superpowers/specs/2026-04-26-sp5-event-loop-design.md §4.1

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "email_domains",
            postgresql.ARRAY(sa.Text),
            nullable=True,
        ),
    )
    # GIN index for "is this domain in any project's email_domains?" lookups
    op.execute(
        "CREATE INDEX idx_projects_email_domains "
        "ON projects USING GIN (email_domains)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_projects_email_domains")
    op.drop_column("projects", "email_domains")
