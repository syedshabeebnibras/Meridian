"""Prompt template contract — Section 8.

The canonical row stored in the prompt registry. Templates are immutable once
activated; rollback is accomplished by reactivating a prior version.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from meridian_contracts.orchestration import ModelTier


class ActivationStatus(StrEnum):
    ACTIVE = "active"
    CANARY = "canary"
    ARCHIVED = "archived"
    DRAFT = "draft"


class TokenBudget(BaseModel):
    """Slot-by-slot token caps enforced by the prompt assembler."""

    model_config = ConfigDict(extra="forbid")

    system: int = Field(ge=0)
    few_shot: int = Field(ge=0)
    retrieval: int = Field(ge=0)
    history: int = Field(ge=0)
    query: int = Field(ge=0)
    total_max: int = Field(ge=0)


class CacheControl(BaseModel):
    """Provider-native cache breakpoints. Section 5 — three-layer cache."""

    model_config = ConfigDict(extra="forbid")

    breakpoints: list[str] = Field(default_factory=list)
    prefix_stable: bool = True


class ActivationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    status: ActivationStatus
    canary_percentage: int = Field(ge=0, le=100, default=0)
    activated_at: datetime
    activated_by: EmailStr


class EvalResults(BaseModel):
    """Rolling eval metrics attached to a template version."""

    model_config = ConfigDict(extra="forbid")

    regression_pass_rate: float = Field(ge=0.0, le=1.0)
    faithfulness_score: float = Field(ge=0.0, le=1.0)
    avg_latency_ms: int = Field(ge=0)


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    model_tier: ModelTier
    min_model: str
    template: str
    parameters: list[str]
    schema_ref: str
    few_shot_dataset: str | None = None
    token_budget: TokenBudget
    cache_control: CacheControl
    activation: ActivationInfo
    eval_results: EvalResults | None = None
