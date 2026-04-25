"""SQLAlchemy ORM models for Meridian application state.

Three concerns addressed here:

  1. Prompt registry (Section 19 D3) — versioned, immutable templates with a
     separate activation table so rollback is a row update, not a DDL event.
  2. Evaluation records (Section 10) — offline + online + golden runs.
  3. Audit log (Section 9 reliability/safety) — every request/response
     traceable for compliance.

Vector columns for the Phase 2 semantic cache are declared here so the
pgvector extension is loaded on the initial migration, but the semantic-cache
table itself is added in Phase 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
    }


# ---------------------------------------------------------------------------
# Prompt registry
# ---------------------------------------------------------------------------
class PromptTemplateRow(Base):
    """Immutable prompt template version (Section 19 D3).

    A row is never mutated after creation. New behaviour = new row with
    version+1. Activation is managed by the PromptActivation table.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_name_version"),
        CheckConstraint("version >= 1", name="ck_prompt_version_pos"),
        Index("ix_prompt_templates_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    min_model: Mapped[str] = mapped_column(String(128), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    schema_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    few_shot_dataset: Mapped[str | None] = mapped_column(String(128))
    token_budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cache_control: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    eval_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(256), nullable=False)

    activations: Mapped[list[PromptActivation]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class PromptActivation(Base):
    """Which prompt version is live in which environment.

    Splitting activation out lets rollback be atomic: flip the active row to
    an earlier template_id and the Prompt Registry serves the previous
    version on the next request, no code deploy required (Section 19 D3).
    """

    __tablename__ = "prompt_activations"
    __table_args__ = (
        Index("ix_prompt_activations_env_status", "environment", "status"),
        CheckConstraint("canary_percentage BETWEEN 0 AND 100", name="ck_activation_canary_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    canary_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_by: Mapped[str] = mapped_column(String(256), nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[PromptTemplateRow] = relationship(back_populates="activations")


# ---------------------------------------------------------------------------
# Evaluation records
# ---------------------------------------------------------------------------
class EvalResultRow(Base):
    """Persisted EvaluationRecord (Section 8 + Section 10)."""

    __tablename__ = "eval_results"
    __table_args__ = (
        Index("ix_eval_results_request", "request_id"),
        Index("ix_eval_results_type_ts", "eval_type", "timestamp"),
        Index("ix_eval_results_prompt_version", "prompt_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    eval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    judge_model: Mapped[str] = mapped_column(String(128), nullable=False)
    judge_prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    golden_answer: Mapped[str | None] = mapped_column(Text)
    human_label: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean)


# ---------------------------------------------------------------------------
# Few-shot example library (Section 6 — Few-shot example management)
# ---------------------------------------------------------------------------
class FewShotExampleRow(Base):
    """One curated example in a few-shot dataset.

    Examples are versioned at the dataset level (e.g. `grounded_qa_examples_v1`)
    and referenced from PromptTemplateRow.few_shot_dataset. Semantic-similarity
    retrieval via pgvector is deferred to Phase 5 (Section 6 — activates when a
    dataset exceeds 20 examples per task type).
    """

    __tablename__ = "few_shot_examples"
    __table_args__ = (
        Index("ix_fewshot_dataset_task", "dataset_name", "task_type"),
        UniqueConstraint("dataset_name", "input_query", name="uq_fewshot_dataset_input"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    input_query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Prompt audit log (Section 6 — Rollback process)
# ---------------------------------------------------------------------------
class PromptAuditLog(Base):
    """Append-only record of registry mutations.

    Separate from the request-level AuditLog below: this tracks *prompt*
    events (create / activate / rollback) for change management, not user
    traffic. Every action that changes what the registry serves writes a row
    here with the acting user and free-form reason.
    """

    __tablename__ = "prompt_audit_log"
    __table_args__ = (Index("ix_prompt_audit_name_ts", "prompt_name", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_version: Mapped[int | None] = mapped_column(Integer)
    to_version: Mapped[int | None] = mapped_column(Integer)
    environment: Mapped[str | None] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """Append-only request/response audit trail for compliance."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_request", "request_id"),
        Index("ix_audit_user_ts", "user_id", "created_at"),
        Index("ix_audit_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(128))
    session_id: Mapped[str | None] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Tenants / auth / server-side sessions (Phase 2)
# ---------------------------------------------------------------------------
# These tables back the multi-tenant SaaS layer: users authenticate, belong
# to workspaces via ``memberships``, and every chat session/message/audit
# event/usage record carries a ``workspace_id`` for isolation.
#
# The enum-style columns (``role``, ``verdict``, message ``role``) are
# constrained text with CHECK constraints rather than Postgres ENUMs so
# future values can be added with a simple CHECK migration instead of an
# ALTER TYPE dance.


class UserRow(Base):
    __tablename__ = "users"
    # Functional unique index on lower(email). The migration is the source
    # of truth; this declaration is just so ORM-level autogenerate sees it.
    __table_args__ = (Index("ix_users_email_lower", text("lower(email)"), unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Nullable so OAuth-only users can be added later without a sentinel.
    password_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list[MembershipRow]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    __table_args__ = (Index("ix_workspaces_owner", "owner_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[MembershipRow]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class MembershipRow(Base):
    """Join table — role per (user, workspace)."""

    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')", name="ck_memberships_role"
        ),
        Index("ix_memberships_workspace", "workspace_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[UserRow] = relationship(back_populates="memberships")
    workspace: Mapped[WorkspaceRow] = relationship(back_populates="memberships")


class ChatSessionRow(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_workspace_updated", "workspace_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_chat_messages_role"),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Stored for assistant messages so the UI can re-render citations +
    # insight panel without another round-trip through the state machine.
    reply: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeedbackRecordRow(Base):
    __tablename__ = "feedback_records"
    __table_args__ = (
        CheckConstraint("verdict IN ('up', 'down')", name="ck_feedback_verdict"),
        Index("ix_feedback_message", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEventRow(Base):
    """Append-only event log scoped to workspace (nullable for system events)."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UsageRecordRow(Base):
    """Per-message cost accounting. Scoped to workspace + user."""

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_workspace_created", "workspace_id", "created_at"),
        Index("ix_usage_records_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[Any] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentRow(Base):
    """Uploaded source file. One per document, workspace-scoped."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('indexing', 'indexed', 'failed')", name="ck_documents_status"),
        Index("ix_documents_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="indexed")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentChunkRow(Base):
    """A single chunk of a document. Embedding column is pgvector and
    declared in raw SQL by migration 0007 — we don't bind a vector type
    here because SQLAlchemy core doesn't ship one. Rows are created via
    raw INSERTs from ``meridian_ingestion``."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_workspace", "workspace_id"),
        Index("ix_document_chunks_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RequestFeedbackRow(Base):
    """Durable sink for /v1/feedback (Phase 3).

    The HTTP contract carries plain string ``request_id``/``user_id`` so this
    table is intentionally decoupled from ``feedback_records`` (which FKs to
    ``chat_messages``). Append-only.
    """

    __tablename__ = "request_feedback"
    __table_args__ = (
        CheckConstraint("verdict IN ('up', 'down')", name="ck_request_feedback_verdict"),
        Index("ix_request_feedback_request_id", "request_id"),
        Index("ix_request_feedback_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    verdict: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Re-export so Alembic's autogenerate sees a single metadata object to diff.
metadata = Base.metadata
# JSON is referenced in some CI paths that lack the postgres dialect; keep the
# import alive so ruff doesn't flag it as unused.
_ = JSON
