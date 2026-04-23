"""semantic_cache — Phase 9 response cache

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The embedding dimension lives in a config so the team can switch between
    # OpenAI (1536), Voyage (1024), etc. Default to 1536 (OpenAI text-embedding-3-small).
    dimension = 1536
    op.execute(
        f"""
        CREATE TABLE semantic_cache (
            id uuid PRIMARY KEY,
            partition_key text NOT NULL,
            query text NOT NULL,
            embedding vector({dimension}) NOT NULL,
            content jsonb NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{{}}',
            stored_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index("ix_semantic_cache_partition_ts", "semantic_cache", ["partition_key", "stored_at"])
    # ivfflat index for approximate nearest-neighbour search. The team tunes
    # `lists` after bootstrap; 100 is a decent default for <1M rows.
    op.execute(
        "CREATE INDEX ix_semantic_cache_embedding "
        "ON semantic_cache USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("semantic_cache")
