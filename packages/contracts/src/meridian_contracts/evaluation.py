"""Evaluation record contract — Section 8.

Written by the evaluator service on both offline regression runs and online
sampled traffic (Section 10).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvaluationType(StrEnum):
    OFFLINE_REGRESSION = "offline_regression"
    ONLINE_SAMPLE = "online_sample"
    GOLDEN_RUN = "golden_run"
    SAFETY_EVAL = "safety_eval"


class EvaluationScores(BaseModel):
    """Judge output. Individual judges may populate a subset of fields."""

    model_config = ConfigDict(extra="forbid")

    faithfulness: float | None = Field(default=None, ge=0.0, le=1.0)
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    response_completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    safety_pass: bool | None = None


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_id: str
    request_id: str
    eval_type: EvaluationType
    scores: EvaluationScores
    judge_model: str
    judge_prompt_version: str
    golden_answer: str | None = None
    human_label: str | None = None
    timestamp: datetime
    prompt_version: str
    model_used: str
    latency_ms: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0)
