"""auth_and_tenants — Phase 2 users/workspaces/memberships + server-side
sessions/messages + audit/usage records

This migration adds the tenant foundation Meridian has been missing. Every
tenant-scoped row carries workspace_id; isolation is enforced at the
service layer by a require_workspace_access dependency.

Design notes
------------
- UUID PKs everywhere (timestamp-ordered uuid7 would be nicer but stdlib
  only ships uuid4; sortable keys are the next refactor).
- ``role`` is a constrained text column rather than a Postgres ENUM to
  keep migrations reversible without an `ALTER TYPE` dance when we add
  future roles.
- Soft delete on ``chat_sessions`` (``deleted_at``) so session lists can
  exclude removed rows without orphaning messages.
- Partial unique index on ``workspaces.slug`` (only when not deleted)
  so deleted slugs can be reused.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # users
    # -----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        # Argon2id-hashed password (PHC string). Nullable so we can add
        # OAuth-only users later without a password column NULL dance.
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    # -----------------------------------------------------------------------
    # workspaces
    # -----------------------------------------------------------------------
    op.create_table(
        "workspaces",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        # URL-safe slug. Unique per non-deleted row (partial index below).
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_workspaces_slug_active "
        "ON workspaces (lower(slug)) WHERE deleted_at IS NULL"
    )
    op.create_index("ix_workspaces_owner", "workspaces", ["owner_user_id"])

    # -----------------------------------------------------------------------
    # memberships — join table with role
    # -----------------------------------------------------------------------
    op.create_table(
        "memberships",
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("user_id", "workspace_id"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_memberships_role",
        ),
    )
    op.create_index("ix_memberships_workspace", "memberships", ["workspace_id"])

    # -----------------------------------------------------------------------
    # chat_sessions
    # -----------------------------------------------------------------------
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chat_sessions_workspace_updated", "chat_sessions", ["workspace_id", sa.text("updated_at DESC")])

    # -----------------------------------------------------------------------
    # chat_messages
    # -----------------------------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # For assistant messages: full OrchestratorReply.model_dump() so the
        # UI can re-render citations / insight panel without another call.
        sa.Column(
            "reply",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_chat_messages_role",
        ),
    )
    op.create_index("ix_chat_messages_session_created", "chat_messages", ["session_id", "created_at"])

    # -----------------------------------------------------------------------
    # feedback_records
    # -----------------------------------------------------------------------
    op.create_table(
        "feedback_records",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("verdict IN ('up', 'down')", name="ck_feedback_verdict"),
    )
    op.create_index("ix_feedback_message", "feedback_records", ["message_id"])

    # -----------------------------------------------------------------------
    # audit_events — append-only event log for compliance + debugging
    # -----------------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_audit_events_workspace_created", "audit_events", ["workspace_id", sa.text("created_at DESC")])
    op.create_index("ix_audit_events_type_created", "audit_events", ["event_type", sa.text("created_at DESC")])

    # -----------------------------------------------------------------------
    # usage_records — per-message cost accounting
    # -----------------------------------------------------------------------
    op.create_table(
        "usage_records",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_usage_records_workspace_created", "usage_records", ["workspace_id", sa.text("created_at DESC")])
    op.create_index("ix_usage_records_user_created", "usage_records", ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("audit_events")
    op.drop_table("feedback_records")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("memberships")
    op.execute("DROP INDEX IF EXISTS ix_workspaces_slug_active")
    op.drop_table("workspaces")
    op.drop_table("users")
