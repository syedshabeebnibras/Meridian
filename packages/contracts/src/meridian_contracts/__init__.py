"""Meridian shared data contracts — source of truth for inter-service payloads.

Every contract here mirrors a schema defined in Section 8 of the execution plan.
Pydantic v2 models are the canonical representation; JSON Schema is derived.
"""

from meridian_contracts.evaluation import EvaluationRecord, EvaluationScores, EvaluationType
from meridian_contracts.model import (
    CacheControlBreakpoint,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ResponseFormat,
)
from meridian_contracts.orchestration import (
    ClassificationResult,
    DispatchInfo,
    Intent,
    ModelTier,
    OrchestrationState,
    OrchestratorPhase,
    PromptAssemblyInfo,
    RetrievalSummary,
    TimingsMs,
)
from meridian_contracts.prompt_template import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    EvalResults,
    PromptTemplate,
    TokenBudget,
)
from meridian_contracts.retrieval import RetrievalResult, RetrievedChunk
from meridian_contracts.telemetry import TelemetryEvent, TelemetryStatus
from meridian_contracts.tool import ToolInvocation, ToolResult, ToolResultStatus, ToolValidation
from meridian_contracts.user_request import ConversationTurn, UserRequest

__all__ = [
    "ActivationInfo",
    "ActivationStatus",
    "CacheControl",
    "CacheControlBreakpoint",
    "ClassificationResult",
    "ConversationTurn",
    "DispatchInfo",
    "EvalResults",
    "EvaluationRecord",
    "EvaluationScores",
    "EvaluationType",
    "Intent",
    "ModelRequest",
    "ModelResponse",
    "ModelTier",
    "ModelUsage",
    "OrchestrationState",
    "OrchestratorPhase",
    "PromptAssemblyInfo",
    "PromptTemplate",
    "ResponseFormat",
    "RetrievalResult",
    "RetrievalSummary",
    "RetrievedChunk",
    "TelemetryEvent",
    "TelemetryStatus",
    "TimingsMs",
    "TokenBudget",
    "ToolInvocation",
    "ToolResult",
    "ToolResultStatus",
    "ToolValidation",
    "UserRequest",
]
