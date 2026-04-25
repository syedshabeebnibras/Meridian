"""Audit sink — append-only event log emitted around every request.

The orchestrator's state machine already records OTel spans for each
phase. This module persists a *durable* summary of every request so we
can answer compliance questions (who asked what, when, what did the
system answer, did guardrails redact/block) after the fact, without
relying on the OTel collector being up.

Two implementations:
  - InMemoryAuditSink — used for tests and the dev escape hatch.
  - PostgresAuditSink — writes to the existing ``audit_log`` table.

Lifecycle events emitted at the API boundary (api.py):
  - ``request.received``  — query, user_id, workspace_id, session_id
  - ``request.completed`` — status, model, cost, classification,
                            retrieval summary, validation, guardrail
                            decisions, error message (if any)
  - ``request.failed``    — exception type + message (no traceback)
  - ``feedback.recorded`` — verdict + request_id

We keep the schema small and stable so callers downstream (eval pipeline,
red-team review) can rely on the keys.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("meridian.audit")


@dataclass(frozen=True)
class AuditEvent:
    request_id: str
    event_type: str
    payload: dict[str, Any]
    user_id: str | None = None
    session_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class AuditSink(Protocol):
    """Pluggable audit backend."""

    def emit(self, event: AuditEvent) -> None: ...


@dataclass
class InMemoryAuditSink:
    events: list[AuditEvent] = field(default_factory=list)

    def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class PostgresAuditSink:
    """Writes to ``audit_log`` (defined in migration 0001).

    Best-effort: a DB failure logs a warning but never bubbles up — we
    don't want the audit sink to take a request down. If audit
    durability becomes a hard requirement we'll switch to a transactional
    outbox.
    """

    session_factory: Callable[[], Session] | sessionmaker[Session]

    def emit(self, event: AuditEvent) -> None:
        # Local import keeps meridian_db an optional runtime dep for the
        # orchestrator package's tests.
        from meridian_db.models import AuditLog

        try:
            with self.session_factory() as session:
                session.add(
                    AuditLog(
                        id=uuid.uuid4(),
                        request_id=event.request_id,
                        user_id=event.user_id,
                        session_id=event.session_id,
                        event_type=event.event_type,
                        payload=event.payload,
                    )
                )
                session.commit()
        except Exception as exc:
            logger.warning(
                "audit sink write failed for event_type=%s request_id=%s: %s",
                event.event_type,
                event.request_id,
                exc,
            )


class NullAuditSink:
    """Drop every event. Used when audit is intentionally disabled."""

    def emit(self, event: AuditEvent) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers — used by api.py to summarise an OrchestratorReply for audit
# ---------------------------------------------------------------------------
def reply_summary(reply: Any) -> dict[str, Any]:
    """Compress an OrchestratorReply into a flat audit payload.

    Loosely typed (Any) to avoid a circular import on OrchestratorReply at
    module load time. We only reach for attributes we know exist.
    """
    state = getattr(reply, "orchestration_state", None)
    classification = getattr(state, "classification", None) if state else None
    retrieval = getattr(state, "retrieval", None) if state else None
    dispatch = getattr(state, "dispatch", None) if state else None
    validation = getattr(reply, "validation", None)
    model_response = getattr(reply, "model_response", None)
    in_g = getattr(reply, "input_guardrail_result", None)
    out_g = getattr(reply, "output_guardrail_result", None)

    payload: dict[str, Any] = {
        "status": getattr(getattr(reply, "status", None), "value", None),
        "cost_usd": str(reply.cost_usd) if getattr(reply, "cost_usd", None) is not None else None,
        "model": getattr(model_response, "model", None) if model_response else None,
        "error_message": getattr(reply, "error_message", None),
    }
    if classification is not None:
        payload["classification"] = {
            "intent": getattr(getattr(classification, "intent", None), "value", None),
            "confidence": getattr(classification, "confidence", None),
        }
    if retrieval is not None:
        payload["retrieval"] = {
            "chunks_retrieved": getattr(retrieval, "chunks_retrieved", None),
            "chunks_after_rerank": getattr(retrieval, "chunks_after_rerank", None),
            "top_relevance_score": getattr(retrieval, "top_relevance_score", None),
        }
    if dispatch is not None:
        payload["dispatch"] = {
            "model": getattr(dispatch, "model", None),
            "attempt": getattr(dispatch, "attempt", None),
        }
    if validation is not None:
        payload["validation"] = {
            "passed": getattr(validation, "passed", None),
        }
    if in_g is not None:
        payload["input_guardrail"] = {
            "decision": getattr(getattr(in_g, "decision", None), "value", None),
        }
    if out_g is not None:
        payload["output_guardrail"] = {
            "decision": getattr(getattr(out_g, "decision", None), "value", None),
        }
    return payload
