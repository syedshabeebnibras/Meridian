"""feature_flags — Phase 8 gradual rollout

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column("percentage", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kill_switch", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("allowlist", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("denylist", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(256), nullable=False, server_default="system"),
        sa.CheckConstraint("percentage BETWEEN 0 AND 100", name="ck_feature_flag_pct"),
    )
    op.execute(
        "INSERT INTO feature_flags (name, percentage, kill_switch) "
        "VALUES ('meridian.enabled', 0, false)"
    )


def downgrade() -> None:
    op.drop_table("feature_flags")
