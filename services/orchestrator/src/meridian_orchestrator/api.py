"""FastAPI HTTP surface for the orchestrator.

Exposes the minimum endpoints needed to deploy Meridian to staging:

  POST /v1/chat   — run a UserRequest through the full state machine
  GET  /healthz   — liveness (always 200 if the process is up)
  GET  /readyz    — readiness (checks template provider + retrieval reachable)
  GET  /metrics   — prometheus text format (stub; Phase 7 team wires real registry)

Orchestrator construction is env-driven via build_orchestrator(). Tests can
pass a pre-built instance.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from meridian_contracts import UserRequest

from meridian_orchestrator.orchestrator import Orchestrator, OrchestratorReply


@dataclass
class AppConfig:
    environment: str = "staging"
    version: str = "0.1.0"


def build_app(
    orchestrator: Orchestrator,
    *,
    config: AppConfig | None = None,
    readiness_check: Callable[[], bool] | None = None,
) -> FastAPI:
    """Build the FastAPI app wrapping a pre-configured Orchestrator.

    `readiness_check` can run any custom probe — e.g. pinging the RAG
    endpoint. Defaults to always-true once the orchestrator is built.
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
        # Phase 7 team wires a real prometheus-client registry. This stub
        # returns the metric names we expect to emit so alerts can reference
        # them before the real counters land.
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
        return orchestrator.handle(request)

    return app
