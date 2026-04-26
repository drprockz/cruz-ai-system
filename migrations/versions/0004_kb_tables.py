"""kb_tables

Add projects and learned_patterns tables for SP2 Knowledge Base.

Spec: docs/superpowers/specs/2026-04-26-sp2-knowledge-base-design.md §3.2

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── projects ──────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("name",        sa.String(100), nullable=False),
        sa.Column("slug",        sa.String(50),  nullable=False, unique=True),
        sa.Column("type",        sa.String(20),  nullable=False),
        sa.Column("status",      sa.String(20),  nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("tech_stack",  sa.JSON,         nullable=True),
        sa.Column("github_url",  sa.Text,         nullable=True),
        sa.Column("local_path",  sa.Text,         nullable=True),
        sa.Column("description", sa.Text,         nullable=True),
        sa.Column("metadata",    sa.JSON,         nullable=True),
        sa.Column("created_at",  sa.TIMESTAMP,    nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",  sa.TIMESTAMP,    nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_projects_status", "projects", ["status"])

    # ── learned_patterns ──────────────────────────────────────────────
    op.create_table(
        "learned_patterns",
        sa.Column("id", sa.String(36), primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        sa.Column("pattern_type",      sa.String(50),  nullable=False),
        sa.Column("content",           sa.Text,        nullable=False),
        sa.Column("source",            sa.String(20),  nullable=False),
        sa.Column("agent_name",        sa.String(50),  nullable=True),
        sa.Column("observation_count", sa.Integer,     nullable=False,
                  server_default=sa.text("1")),
        sa.Column("confidence",        sa.Float,       nullable=False,
                  server_default=sa.text("1.0")),
        sa.Column("qdrant_id",         sa.String(36),  nullable=True),
        sa.Column("active",            sa.Boolean,     nullable=False,
                  server_default=sa.text("TRUE")),
        sa.Column("created_at",        sa.TIMESTAMP,   nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",        sa.TIMESTAMP,   nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_learned_patterns_type",
                    "learned_patterns", ["pattern_type", "active"])
    op.create_index("idx_learned_patterns_src",
                    "learned_patterns", ["source", "observation_count"])
    op.create_unique_constraint(
        "uq_learned_patterns_key",
        "learned_patterns",
        ["pattern_type", "content", "source"],
    )

    # ── seed projects ─────────────────────────────────────────────────
    op.execute("""
        INSERT INTO projects (id, name, slug, type, status) VALUES
            (gen_random_uuid()::text, 'AMA Solutions',  'ama-solutions',  'client',   'active'),
            (gen_random_uuid()::text, 'Shooterista',    'shooterista',    'client',   'active'),
            (gen_random_uuid()::text, 'SuiteAdvisors',  'suiteadvisors',  'client',   'active'),
            (gen_random_uuid()::text, 'Asia Capital',   'asia-capital',   'client',   'active'),
            (gen_random_uuid()::text, 'MIDAR',          'midar',          'personal', 'active')
    """)


def downgrade() -> None:
    op.drop_constraint("uq_learned_patterns_key", "learned_patterns", type_="unique")
    op.drop_index("idx_learned_patterns_src",  table_name="learned_patterns")
    op.drop_index("idx_learned_patterns_type", table_name="learned_patterns")
    op.drop_table("learned_patterns")

    op.drop_index("idx_projects_status", table_name="projects")
    op.drop_table("projects")
