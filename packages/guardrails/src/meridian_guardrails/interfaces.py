"""Typed Protocols for the guardrail pipeline.

Section 5 specifies guardrails run as inline middleware. Each guardrail
returns a `GuardrailOutcome` that the orchestrator translates into state
transitions (continue / redact / refuse).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class GuardrailDecision(StrEnum):
    PASS = "pass"
    REDACT = "redact"
    BLOCK = "block"


class GuardrailOutcome(BaseModel):
    """Return value of any guardrail."""

    decision: GuardrailDecision
    reason: str = Field(default="", description="Short human-readable rationale.")
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    redacted_content: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class InputGuardrail(Protocol):
    """Runs before the model sees user input.

    Sync for consistency with the Phase 3 orchestrator. Async variants
    can be added later if the pipeline needs to parallelise expensive
    remote checks.
    """

    name: str

    def check(self, text: str) -> GuardrailOutcome: ...


class OutputGuardrail(Protocol):
    """Runs after the model produces output, before it reaches the user."""

    name: str

    def check(self, text: str, *, context: dict[str, str]) -> GuardrailOutcome: ...
