"""request_feedback — durable log for /v1/feedback (Phase 3)

The Phase 2 ``feedback_records`` table requires ``message_id``/``user_id`` as
UUIDs and FKs into ``chat_messages``/``users``. The /v1/feedback HTTP
contract still carries plain string ``request_id`` + ``user_id`` so existing
callers (eval pipeline, red-team scripts) keep working without a schema
break. This table is the durable sink for that contract — append-only,
indexed by request_id and (user_id, created_at).

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_feedback",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("verdict IN ('up', 'down')", name="ck_request_feedback_verdict"),
    )
    op.create_index(
        "ix_request_feedback_request_id", "request_feedback", ["request_id"]
    )
    op.create_index(
        "ix_request_feedback_user_created",
        "request_feedback",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_request_feedback_user_created", table_name="request_feedback")
    op.drop_index("ix_request_feedback_request_id", table_name="request_feedback")
    op.drop_table("request_feedback")
