"""FastAPI HTTP surface for the orchestrator.

Endpoints:
  POST /v1/chat                       — run a UserRequest through the state machine
  POST /v1/feedback                   — thumbs up/down + free-text on a message
  POST /v1/sessions                   — create a chat session in the caller's workspace
  GET  /v1/sessions                   — list sessions in the caller's workspace
  GET  /v1/sessions/{id}              — get one session (workspace-scoped)
  GET  /v1/sessions/{id}/messages     — list messages in a session
  PATCH /v1/sessions/{id}             — rename a session
  DELETE /v1/sessions/{id}            — soft-delete a session
  GET  /healthz /readyz /metrics      — platform probes (unauthenticated)

Tenant mode (Phase 2):
    When a ``session_service`` is supplied to ``build_app``, every
    /v1/... route except /v1/chat (for back-compat with legacy callers)
    requires a verified ``CallerContext``. /v1/chat also requires a
    session_id that maps to a session owned by the caller's workspace.

Legacy mode:
    When ``session_service`` is None, /v1/chat accepts the raw
    ``UserRequest`` as before — used by older unit tests. Do not run in
    production.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol

from fastapi import Depends, FastAPI, HTTPException, Path
from fastapi.responses import PlainTextResponse, Response
from meridian_contracts import UserRequest
from meridian_feature_flags import RolloutService
from meridian_ops import RateLimitExceededError, TokenBucketRateLimiter
from pydantic import BaseModel, ConfigDict, Field

from meridian_orchestrator import metrics
from meridian_orchestrator.auth import InternalAuthConfig, build_require_internal_key
from meridian_orchestrator.caller import CallerContext
from meridian_orchestrator.orchestrator import Orchestrator, OrchestratorReply
from meridian_orchestrator.sessions import (
    ChatMessageSummary,
    ChatSessionSummary,
    PersistRequest,
    SessionNotFoundError,
    SessionService,
)


@dataclass
class AppConfig:
    environment: str = "staging"
    version: str = "0.1.0"
    flag_name: str = "meridian.enabled"


# ---------------------------------------------------------------------------
# Inbound request schemas (tenant-aware flow)
# ---------------------------------------------------------------------------
class ChatInput(BaseModel):
    """Minimal payload from the Next.js proxy after it resolves identity."""

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    query: str = Field(min_length=1, max_length=4000)
    metadata: dict[str, str] = Field(default_factory=dict)


class CreateSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New chat", max_length=128)


class RenameSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=128)


class SessionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_summary(cls, s: ChatSessionSummary) -> SessionDTO:
        return cls(
            id=s.id,
            workspace_id=s.workspace_id,
            user_id=s.user_id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class MessageDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    reply: dict | None  # type: ignore[type-arg]
    created_at: datetime

    @classmethod
    def from_summary(cls, m: ChatMessageSummary) -> MessageDTO:
        return cls(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            reply=m.reply,
            created_at=m.created_at,
        )


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    user_id: str
    verdict: Literal["up", "down"]
    comment: str = Field(default="", max_length=2000)


class FeedbackAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_at: datetime
    request_id: str


class FeedbackStore(Protocol):
    """Anything that can persist a feedback record. Phase 3 adds a
    Postgres-backed implementation."""

    def record(self, feedback: FeedbackRequest) -> None: ...


@dataclass
class InMemoryFeedbackStore:
    entries: list[FeedbackRequest] | None = None

    def __post_init__(self) -> None:
        if self.entries is None:
            self.entries = []

    def record(self, feedback: FeedbackRequest) -> None:
        assert self.entries is not None
        self.entries.append(feedback)


# ---------------------------------------------------------------------------
# build_app
# ---------------------------------------------------------------------------
def build_app(
    orchestrator: Orchestrator,
    *,
    config: AppConfig | None = None,
    readiness_check: Callable[[], bool] | None = None,
    rollout: RolloutService | None = None,
    feedback_store: FeedbackStore | None = None,
    rate_limiter: TokenBucketRateLimiter | None = None,
    auth_config: InternalAuthConfig | None = None,
    session_service: SessionService | None = None,
    require_caller: Callable[..., CallerContext] | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``session_service`` + ``require_caller`` are required together for the
    Phase 2 tenant-aware flow. When both are None, the legacy /v1/chat
    path is exposed without tenancy (used by older unit tests).
    """
    config = config or AppConfig(environment=os.environ.get("MERIDIAN_ENV", "staging"))
    auth_config = auth_config or InternalAuthConfig.from_env()
    require_internal_key = build_require_internal_key(auth_config)

    app = FastAPI(
        title="Meridian Orchestrator",
        version=config.version,
        docs_url="/docs",
        redoc_url=None,
    )

    # ------------------------------------------------------------------
    # Platform probes (open)
    # ------------------------------------------------------------------
    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    @app.get("/readyz", response_class=PlainTextResponse)
    def readyz() -> str:
        if readiness_check is not None and not readiness_check():
            raise HTTPException(status_code=503, detail="not ready")
        return "ready"

    @app.get("/metrics")
    def metrics_endpoint() -> Response:
        return Response(
            content=metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Chat — tenant-aware when session_service is wired, legacy otherwise
    # ------------------------------------------------------------------
    if session_service is not None and require_caller is not None:

        @app.post(
            "/v1/chat",
            response_model=None,
            dependencies=[Depends(require_internal_key)],
        )
        def chat_tenant(
            payload: ChatInput,
            caller: CallerContext = Depends(require_caller),
        ) -> OrchestratorReply:
            # Verify the session belongs to the caller's workspace before
            # burning any model budget.
            try:
                session_service.get_session(
                    session_id=payload.session_id, workspace_id=caller.workspace_id
                )
            except SessionNotFoundError as exc:
                raise HTTPException(status_code=404, detail="session not found") from exc

            if rate_limiter is not None:
                try:
                    rate_limiter.allow(f"{caller.workspace_id}:{caller.user_id}")
                except RateLimitExceededError as rle:
                    metrics.RATE_LIMITED_TOTAL.inc()
                    raise HTTPException(
                        status_code=429,
                        detail=str(rle),
                        headers={"Retry-After": "1"},
                    ) from rle

            user_request = UserRequest(
                request_id=f"req_{uuid.uuid4().hex[:24]}",
                user_id=str(caller.user_id),
                session_id=str(payload.session_id),
                query=payload.query,
                conversation_history=[],
                metadata={**payload.metadata, "workspace_id": str(caller.workspace_id)},
            )

            started = time.perf_counter()
            reply = orchestrator.handle(user_request)
            metrics.REQUEST_DURATION_SECONDS.observe(time.perf_counter() - started)
            metrics.REQUESTS_TOTAL.labels(status=reply.status.value).inc()
            if reply.cost_usd is not None:
                metrics.COST_USD_TOTAL.inc(reply.cost_usd)

            # Persist the exchange (messages + audit event + usage record).
            if reply.status.value == "ok":
                usage = reply.model_response.usage if reply.model_response else None
                session_service.persist_exchange(
                    PersistRequest(
                        session_id=payload.session_id,
                        workspace_id=caller.workspace_id,
                        user_id=caller.user_id,
                        query=payload.query,
                        reply_json=reply.model_dump(mode="json"),
                        model=reply.model_response.model if reply.model_response else "unknown",
                        input_tokens=usage.input_tokens if usage else 0,
                        output_tokens=usage.output_tokens if usage else 0,
                        cost_usd=Decimal(str(reply.cost_usd or 0)),
                    )
                )
            return reply

        # --- Session CRUD -----------------------------------------------------
        @app.post(
            "/v1/sessions",
            response_model=SessionDTO,
            dependencies=[Depends(require_internal_key)],
        )
        def create_session(
            payload: CreateSessionInput,
            caller: CallerContext = Depends(require_caller),
        ) -> SessionDTO:
            summary = session_service.create_session(
                workspace_id=caller.workspace_id,
                user_id=caller.user_id,
                title=payload.title,
            )
            return SessionDTO.from_summary(summary)

        @app.get(
            "/v1/sessions",
            response_model=list[SessionDTO],
            dependencies=[Depends(require_internal_key)],
        )
        def list_sessions(
            caller: CallerContext = Depends(require_caller),
        ) -> list[SessionDTO]:
            return [
                SessionDTO.from_summary(s)
                for s in session_service.list_sessions(workspace_id=caller.workspace_id)
            ]

        @app.get(
            "/v1/sessions/{session_id}",
            response_model=SessionDTO,
            dependencies=[Depends(require_internal_key)],
        )
        def get_session_route(
            session_id: uuid.UUID = Path(...),
            caller: CallerContext = Depends(require_caller),
        ) -> SessionDTO:
            try:
                summary = session_service.get_session(
                    session_id=session_id, workspace_id=caller.workspace_id
                )
            except SessionNotFoundError as exc:
                raise HTTPException(status_code=404, detail="session not found") from exc
            return SessionDTO.from_summary(summary)

        @app.get(
            "/v1/sessions/{session_id}/messages",
            response_model=list[MessageDTO],
            dependencies=[Depends(require_internal_key)],
        )
        def list_messages(
            session_id: uuid.UUID = Path(...),
            caller: CallerContext = Depends(require_caller),
        ) -> list[MessageDTO]:
            try:
                msgs = session_service.list_messages(
                    session_id=session_id, workspace_id=caller.workspace_id
                )
            except SessionNotFoundError as exc:
                raise HTTPException(status_code=404, detail="session not found") from exc
            return [MessageDTO.from_summary(m) for m in msgs]

        @app.patch(
            "/v1/sessions/{session_id}",
            response_model=SessionDTO,
            dependencies=[Depends(require_internal_key)],
        )
        def rename_session(
            payload: RenameSessionInput,
            session_id: uuid.UUID = Path(...),
            caller: CallerContext = Depends(require_caller),
        ) -> SessionDTO:
            try:
                summary = session_service.rename_session(
                    session_id=session_id,
                    workspace_id=caller.workspace_id,
                    user_id=caller.user_id,
                    title=payload.title,
                )
            except SessionNotFoundError as exc:
                raise HTTPException(status_code=404, detail="session not found") from exc
            return SessionDTO.from_summary(summary)

        @app.delete(
            "/v1/sessions/{session_id}",
            status_code=204,
            dependencies=[Depends(require_internal_key)],
        )
        def delete_session(
            session_id: uuid.UUID = Path(...),
            caller: CallerContext = Depends(require_caller),
        ) -> Response:
            try:
                session_service.soft_delete_session(
                    session_id=session_id,
                    workspace_id=caller.workspace_id,
                    user_id=caller.user_id,
                )
            except SessionNotFoundError as exc:
                raise HTTPException(status_code=404, detail="session not found") from exc
            return Response(status_code=204)

    else:
        # -------- Legacy mode (no tenant wiring) -----------------------------
        @app.post(
            "/v1/chat",
            response_model=None,
            dependencies=[Depends(require_internal_key)],
        )
        def chat_legacy(request: UserRequest) -> OrchestratorReply:
            if rate_limiter is not None:
                try:
                    rate_limiter.allow(request.user_id)
                except RateLimitExceededError as exc:
                    metrics.RATE_LIMITED_TOTAL.inc()
                    raise HTTPException(
                        status_code=429,
                        detail=str(exc),
                        headers={"Retry-After": "1"},
                    ) from exc
            if rollout is not None:
                decision = rollout.evaluate(config.flag_name, request.user_id)
                if not decision.allowed:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "Meridian is not enabled for your account yet. "
                            f"(rollout: {decision.result.value})"
                        ),
                    )
            started = time.perf_counter()
            reply = orchestrator.handle(request)
            metrics.REQUEST_DURATION_SECONDS.observe(time.perf_counter() - started)
            metrics.REQUESTS_TOTAL.labels(status=reply.status.value).inc()
            if reply.cost_usd is not None:
                metrics.COST_USD_TOTAL.inc(reply.cost_usd)
            return reply

    # ------------------------------------------------------------------
    # Feedback — always available; in-memory when no feedback_store
    # ------------------------------------------------------------------
    @app.post(
        "/v1/feedback",
        response_model=None,
        dependencies=[Depends(require_internal_key)],
    )
    def feedback(request: FeedbackRequest) -> FeedbackAck:
        if feedback_store is None:
            raise HTTPException(status_code=501, detail="feedback collection not configured")
        feedback_store.record(request)
        return FeedbackAck(recorded_at=datetime.now(tz=UTC), request_id=request.request_id)

    return app
