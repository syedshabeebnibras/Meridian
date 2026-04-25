"""documents + document_chunks — Phase 6 local ingestion path

Two tables, both workspace-scoped, both append-only on the chunk side:

  documents         one row per uploaded source file
  document_chunks   N rows per document, with vector embeddings for ANN search

Embedding dimension matches ``semantic_cache`` (1536, OpenAI
text-embedding-3-small). The dev/test path uses the deterministic
``StaticEmbedding`` from meridian_semantic_cache, which produces a
configurable smaller dimension; in test environments the migration is run
with ``MERIDIAN_DOC_EMBEDDING_DIM`` set to that smaller number, but in
prod the default 1536 holds.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-25
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dimension = int(os.environ.get("MERIDIAN_DOC_EMBEDDING_DIM", "1536"))

    op.create_table(
        "documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="indexed"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('indexing', 'indexed', 'failed')",
            name="ck_documents_status",
        ),
    )
    op.create_index(
        "ix_documents_workspace_created", "documents", ["workspace_id", "created_at"]
    )

    op.execute(
        f"""
        CREATE TABLE document_chunks (
            id uuid PRIMARY KEY,
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            chunk_index int NOT NULL,
            content text NOT NULL,
            content_tokens int NOT NULL DEFAULT 0,
            embedding vector({dimension}) NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{{}}',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index(
        "ix_document_chunks_workspace", "document_chunks", ["workspace_id"]
    )
    op.create_index(
        "ix_document_chunks_document", "document_chunks", ["document_id"]
    )
    # ANN index for nearest-neighbour search; `lists=100` is the default
    # tuning for <1M rows. Operators retune as the corpus grows.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document", table_name="document_chunks")
    op.drop_index("ix_document_chunks_workspace", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_workspace_created", table_name="documents")
    op.drop_table("documents")
