"""FastAPI HTTP surface for the orchestrator.

Endpoints:
  POST /v1/chat     — run a UserRequest through the state machine, gated
                      by the feature-flag rollout if one is wired in
  POST /v1/feedback — record thumbs up/down + free-text for a past request
  GET  /healthz     — liveness
  GET  /readyz      — readiness (checks template provider + retrieval)
  GET  /metrics     — prometheus text format (stub)

Orchestrator + optional rollout + feedback store are injected at build time.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from meridian_contracts import UserRequest
from meridian_feature_flags import RolloutService
from meridian_ops import RateLimitExceededError, TokenBucketRateLimiter
from pydantic import BaseModel, ConfigDict, Field

from meridian_orchestrator.orchestrator import Orchestrator, OrchestratorReply


@dataclass
class AppConfig:
    environment: str = "staging"
    version: str = "0.1.0"
    flag_name: str = "meridian.enabled"


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
    """Anything that can persist a feedback record. Phase 8 ships an
    InMemoryFeedbackStore; Phase 9 adds a Postgres-backed one."""

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


def build_app(
    orchestrator: Orchestrator,
    *,
    config: AppConfig | None = None,
    readiness_check: Callable[[], bool] | None = None,
    rollout: RolloutService | None = None,
    feedback_store: FeedbackStore | None = None,
    rate_limiter: TokenBucketRateLimiter | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    `rollout`: optional; if provided, /v1/chat returns 403 for users not in
    the rollout. When None, every request is allowed (useful for tests).

    `feedback_store`: optional; if None, /v1/feedback returns 501.

    `rate_limiter`: optional per-user token-bucket. When provided, /v1/chat
    returns 429 with a Retry-After header if the user is over their burst.
    """
    config = config or AppConfig(environment=os.environ.get("MERIDIAN_ENV", "staging"))

    app = FastAPI(
        title="Meridian Orchestrator",
        version=config.version,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    @app.get("/readyz", response_class=PlainTextResponse)
    def readyz() -> str:
        if readiness_check is not None and not readiness_check():
            raise HTTPException(status_code=503, detail="not ready")
        return "ready"

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        return (
            "# HELP meridian_requests_total Total orchestrator requests\n"
            "# TYPE meridian_requests_total counter\n"
            "meridian_requests_total 0\n"
            "# HELP meridian_cost_usd_total Total USD cost accounted\n"
            "# TYPE meridian_cost_usd_total counter\n"
            "meridian_cost_usd_total 0\n"
        )

    @app.post("/v1/chat", response_model=None)
    def chat(request: UserRequest) -> OrchestratorReply:
        if rate_limiter is not None:
            try:
                rate_limiter.allow(request.user_id)
            except RateLimitExceededError as exc:
                # Retry-After of 1s — matches the default refill rate. Clients
                # doing exponential backoff will quickly find the sustained rate.
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
        return orchestrator.handle(request)

    @app.post("/v1/feedback", response_model=None)
    def feedback(request: FeedbackRequest) -> FeedbackAck:
        if feedback_store is None:
            raise HTTPException(status_code=501, detail="feedback collection not configured")
        feedback_store.record(request)
        return FeedbackAck(recorded_at=datetime.now(tz=UTC), request_id=request.request_id)

    return app
