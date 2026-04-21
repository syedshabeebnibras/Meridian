"""Orchestration state contract — Section 8.

Represents the live state of a request as it flows through the state machine
(classify → retrieve → assemble → dispatch → validate → shape).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    """Request classifications produced by the small-tier classifier.

    Categories match Section 6's classifier prompt design, which supersedes
    the summary in Section 5 §3. `chitchat`-style queries fall under
    `out_of_scope` or `clarification` depending on whether a follow-up is
    worth asking.
    """

    GROUNDED_QA = "grounded_qa"
    EXTRACTION = "extraction"
    TOOL_ACTION = "tool_action"
    CLARIFICATION = "clarification"
    OUT_OF_SCOPE = "out_of_scope"


class ModelTier(StrEnum):
    """Three-tier routing cascade — Section 19 Decision 4."""

    SMALL = "small"
    MID = "mid"
    FRONTIER = "frontier"


class OrchestratorPhase(StrEnum):
    """State machine phases. Matches the lifecycle diagram in Section 5."""

    RECEIVED = "RECEIVED"
    INPUT_GUARDRAILS = "INPUT_GUARDRAILS"
    CLASSIFIED = "CLASSIFIED"
    RETRIEVED = "RETRIEVED"
    ASSEMBLED = "ASSEMBLED"
    DISPATCHED = "DISPATCHED"
    VALIDATED = "VALIDATED"
    OUTPUT_GUARDRAILS = "OUTPUT_GUARDRAILS"
    SHAPED = "SHAPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    model_tier: ModelTier
    workflow: str


class RetrievalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_rewritten: str
    chunks_retrieved: int = Field(ge=0)
    chunks_after_rerank: int = Field(ge=0)
    top_relevance_score: float = Field(ge=0.0, le=1.0)


class PromptAssemblyInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_name: str
    template_version: int = Field(ge=1)
    total_tokens_assembled: int = Field(ge=0)
    cache_prefix_tokens: int = Field(ge=0)


class DispatchInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str
    attempt: int = Field(ge=1)
    idempotency_key: str


class TimingsMs(BaseModel):
    """Per-stage timings in milliseconds. Nullable while the stage is pending."""

    model_config = ConfigDict(extra="forbid")

    input_guardrails: int | None = None
    classification: int | None = None
    retrieval: int | None = None
    assembly: int | None = None
    dispatch_pending: int | None = None
    validation: int | None = None
    output_guardrails: int | None = None
    total: int | None = None


class OrchestrationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    current_state: OrchestratorPhase
    classification: ClassificationResult | None = None
    retrieval: RetrievalSummary | None = None
    prompt: PromptAssemblyInfo | None = None
    dispatch: DispatchInfo | None = None
    timings_ms: TimingsMs = Field(default_factory=TimingsMs)
    errors: list[str] = Field(default_factory=list)
