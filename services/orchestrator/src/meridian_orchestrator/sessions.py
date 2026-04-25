"""Server-side chat session + message service.

Owns every tenant-scoped write to ``chat_sessions``, ``chat_messages``,
``audit_events``, and ``usage_records``. The API layer never touches
SQLAlchemy directly — it calls this service so isolation rules live in
one place.

Every read / write enforces ``workspace_id``. Passing a session_id from
a different workspace yields ``NotFoundError`` — we never let the caller
distinguish "doesn't exist" from "belongs to someone else".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from meridian_db.models import (
    AuditEventRow,
    ChatMessageRow,
    ChatSessionRow,
    UsageRecordRow,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker


class SessionNotFoundError(LookupError):
    """Raised when a session doesn't exist in the caller's workspace."""


@dataclass(frozen=True)
class ChatSessionSummary:
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ChatMessageSummary:
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    reply: dict[str, Any] | None
    created_at: datetime


@dataclass
class PersistRequest:
    session_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    query: str
    reply_json: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class SessionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    def create_session(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> ChatSessionSummary:
        title = title.strip()[:128] or "New chat"
        with self._session_factory.begin() as session:
            row = ChatSessionRow(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                user_id=user_id,
                title=title,
            )
            session.add(row)
            session.flush()
            self._append_audit_locked(
                session,
                workspace_id=workspace_id,
                user_id=user_id,
                event_type="chat_session.created",
                payload={"session_id": str(row.id)},
            )
            return _session_summary(row)

    def list_sessions(self, *, workspace_id: uuid.UUID) -> list[ChatSessionSummary]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChatSessionRow)
                .where(ChatSessionRow.workspace_id == workspace_id)
                .where(ChatSessionRow.deleted_at.is_(None))
                .order_by(ChatSessionRow.updated_at.desc())
                .limit(200)
            ).all()
            return [_session_summary(r) for r in rows]

    def get_session(self, *, session_id: uuid.UUID, workspace_id: uuid.UUID) -> ChatSessionSummary:
        with self._session_factory() as session:
            row = self._load_session(session, session_id=session_id, workspace_id=workspace_id)
            return _session_summary(row)

    def rename_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
    ) -> ChatSessionSummary:
        title = title.strip()[:128]
        if not title:
            raise ValueError("title required")
        with self._session_factory.begin() as session:
            row = self._load_session(session, session_id=session_id, workspace_id=workspace_id)
            row.title = title
            row.updated_at = datetime.now(tz=UTC)
            self._append_audit_locked(
                session,
                workspace_id=workspace_id,
                user_id=user_id,
                event_type="chat_session.renamed",
                payload={"session_id": str(row.id), "new_title": title},
            )
            return _session_summary(row)

    def soft_delete_session(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        with self._session_factory.begin() as session:
            row = self._load_session(session, session_id=session_id, workspace_id=workspace_id)
            row.deleted_at = datetime.now(tz=UTC)
            self._append_audit_locked(
                session,
                workspace_id=workspace_id,
                user_id=user_id,
                event_type="chat_session.deleted",
                payload={"session_id": str(row.id)},
            )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def list_messages(
        self, *, session_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[ChatMessageSummary]:
        with self._session_factory() as session:
            # Verify ownership first. list_messages is a read, but we still
            # refuse cross-workspace access the same way writes do.
            self._load_session(session, session_id=session_id, workspace_id=workspace_id)
            rows = session.scalars(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.created_at)
            ).all()
            return [_message_summary(r) for r in rows]

    def persist_exchange(self, request: PersistRequest) -> tuple[uuid.UUID, uuid.UUID]:
        """Persist a (user, assistant) pair plus the usage record and audit event.

        Returns ``(user_message_id, assistant_message_id)``.
        """
        with self._session_factory.begin() as session:
            row = self._load_session(
                session,
                session_id=request.session_id,
                workspace_id=request.workspace_id,
            )
            now = datetime.now(tz=UTC)
            user_msg = ChatMessageRow(
                id=uuid.uuid4(),
                session_id=row.id,
                role="user",
                content=request.query,
                reply=None,
            )
            assistant_msg = ChatMessageRow(
                id=uuid.uuid4(),
                session_id=row.id,
                role="assistant",
                content=_extract_answer(request.reply_json),
                reply=request.reply_json,
            )
            session.add(user_msg)
            session.add(assistant_msg)
            session.flush()
            row.updated_at = now

            usage = UsageRecordRow(
                id=uuid.uuid4(),
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                message_id=assistant_msg.id,
                model=request.model,
                input_tokens=request.input_tokens,
                output_tokens=request.output_tokens,
                cost_usd=request.cost_usd,
            )
            session.add(usage)

            self._append_audit_locked(
                session,
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                event_type="chat.exchange",
                payload={
                    "session_id": str(row.id),
                    "user_message_id": str(user_msg.id),
                    "assistant_message_id": str(assistant_msg.id),
                    "model": request.model,
                    "cost_usd": str(request.cost_usd),
                    "input_tokens": request.input_tokens,
                    "output_tokens": request.output_tokens,
                },
            )
            return user_msg.id, assistant_msg.id

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _load_session(
        self, session: Session, *, session_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> ChatSessionRow:
        row = session.scalar(
            select(ChatSessionRow)
            .where(ChatSessionRow.id == session_id)
            .where(ChatSessionRow.workspace_id == workspace_id)
            .where(ChatSessionRow.deleted_at.is_(None))
        )
        if row is None:
            # Identical response for "doesn't exist" and "belongs to other
            # workspace" — no information leak.
            raise SessionNotFoundError(str(session_id))
        return row

    def _append_audit_locked(
        self,
        session: Session,
        *,
        workspace_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Append an audit event within an open transaction."""
        session.add(
            AuditEventRow(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                user_id=user_id,
                event_type=event_type,
                payload=payload,
            )
        )


def _session_summary(row: ChatSessionRow) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=row.id,
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_summary(row: ChatMessageRow) -> ChatMessageSummary:
    return ChatMessageSummary(
        id=row.id,
        session_id=row.session_id,
        role=row.role,
        content=row.content,
        reply=row.reply,
        created_at=row.created_at,
    )


def _extract_answer(reply: dict[str, Any]) -> str:
    """Pull the natural-language answer out of an OrchestratorReply JSON blob.

    Mirrors ``meridian_orchestrator.orchestrator._extract_answer_text`` but
    operates on a plain dict (what we persist).
    """
    model_response = reply.get("model_response") or {}
    content = model_response.get("content")
    if isinstance(content, dict):
        answer = content.get("answer")
        if isinstance(answer, str):
            return answer
    if isinstance(content, str):
        return content
    return str(reply.get("error_message") or "")
