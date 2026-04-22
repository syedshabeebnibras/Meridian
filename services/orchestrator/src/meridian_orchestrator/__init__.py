"""Meridian orchestration service.

Deterministic state machine (Section 5 + Section 7). Phase 3 ships the sync
handle_request flow with mock retrieval, stubbed guardrails, and the full
retry / validation / routing logic. Phase 4 wires real retrieval + tools;
Phase 5 wires real guardrails.
"""

__version__ = "0.1.0"

from meridian_orchestrator.api import (
    AppConfig,
    FeedbackAck,
    FeedbackRequest,
    FeedbackStore,
    InMemoryFeedbackStore,
    build_app,
)
from meridian_orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorReply,
    OrchestratorStatus,
    TemplateProvider,
)
from meridian_orchestrator.routing import route_tier

__all__ = [
    "AppConfig",
    "FeedbackAck",
    "FeedbackRequest",
    "FeedbackStore",
    "InMemoryFeedbackStore",
    "Orchestrator",
    "OrchestratorConfig",
    "OrchestratorReply",
    "OrchestratorStatus",
    "TemplateProvider",
    "build_app",
    "route_tier",
]
