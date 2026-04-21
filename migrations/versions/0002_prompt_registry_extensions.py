"""prompt registry extensions — few-shot examples + prompt audit log

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # few_shot_examples — versioned at the dataset level (Section 6).
    op.create_table(
        "few_shot_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_name", sa.String(128), nullable=False),
        sa.Column("input_query", sa.Text, nullable=False),
        sa.Column("expected_output", postgresql.JSONB, nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column(
            "difficulty", sa.String(16), nullable=False, server_default="medium"
        ),
        sa.Column("source", sa.String(256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dataset_name", "input_query", name="uq_fewshot_dataset_input"
        ),
    )
    op.create_index(
        "ix_fewshot_dataset_task",
        "few_shot_examples",
        ["dataset_name", "task_type"],
    )

    # prompt_audit_log — append-only record of registry mutations.
    op.create_table(
        "prompt_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_name", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_version", sa.Integer),
        sa.Column("to_version", sa.Integer),
        sa.Column("environment", sa.String(32)),
        sa.Column("actor", sa.String(256), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_prompt_audit_name_ts",
        "prompt_audit_log",
        ["prompt_name", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("prompt_audit_log")
    op.drop_table("few_shot_examples")
