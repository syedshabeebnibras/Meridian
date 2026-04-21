"""Dataset schemas for the regression suite.

Datasets are YAML files under ``datasets/``. Two shapes are supported in
Phase 2 — classifier and grounded_qa. See REGRESSION.md for the full format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from meridian_contracts import Intent, ModelTier
from pydantic import BaseModel, ConfigDict, Discriminator, Field


class _StubResponse(BaseModel):
    """Canned model response for offline (CI) regression runs."""

    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any] | str
    latency_ms: int = 100


class ClassifierExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    expected_intent: Intent
    expected_tier: ModelTier | None = None
    stub_response: _StubResponse | None = None


class _RetrievedDocFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    content: str
    relevance: float = Field(ge=0.0, le=1.0)


class GoldenQAExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    retrieved_docs: list[_RetrievedDocFixture] = Field(default_factory=list)
    golden_answer: str
    expected_citations: list[str] = Field(default_factory=list)
    stub_response: _StubResponse | None = None


class _ClassifierDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    task_type: Literal["classifier"]
    prompt_name: str = "classifier"
    examples: list[ClassifierExample]


class _GoldenQADataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    task_type: Literal["grounded_qa"]
    prompt_name: str = "grounded_qa"
    system_vars: dict[str, str] = Field(default_factory=dict)
    examples: list[GoldenQAExample]


Dataset = Annotated[
    _ClassifierDataset | _GoldenQADataset,
    Discriminator("task_type"),
]


def load_dataset(path: Path) -> Dataset:
    """Parse a YAML dataset file, returning a validated Pydantic model."""
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    task_type = raw.get("task_type")
    if task_type == "classifier":
        return _ClassifierDataset.model_validate(raw)
    if task_type == "grounded_qa":
        return _GoldenQADataset.model_validate(raw)
    raise ValueError(f"{path}: unknown task_type {task_type!r}")
