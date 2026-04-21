"""GuardrailPipeline — chain multiple guardrails and combine their decisions.

Precedence (strictest wins):   BLOCK > REDACT > PASS

REDACT propagates — if a guardrail returned redacted text, later guardrails
see the redacted version, not the original. This matters for input
guardrails (PII redaction) where we want the model to never see the raw
sensitive content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from meridian_guardrails.interfaces import (
    GuardrailDecision,
    GuardrailOutcome,
    InputGuardrail,
    OutputGuardrail,
)

_STRICTNESS = {
    GuardrailDecision.PASS: 0,
    GuardrailDecision.REDACT: 1,
    GuardrailDecision.BLOCK: 2,
}


class PipelineResult(BaseModel):
    """Aggregated result across every guardrail in the pipeline."""

    model_config = ConfigDict(extra="forbid")

    decision: GuardrailDecision
    effective_text: str
    outcomes: list[GuardrailOutcome] = Field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return self.decision is GuardrailDecision.BLOCK

    @property
    def was_redacted(self) -> bool:
        return self.decision is GuardrailDecision.REDACT


@dataclass
class GuardrailPipeline:
    """Ordered list of guardrails. Short-circuits on BLOCK."""

    guardrails: list[Any] = field(default_factory=list)

    def check_input(self, text: str) -> PipelineResult:
        outcomes: list[GuardrailOutcome] = []
        current_text = text
        current_decision = GuardrailDecision.PASS
        for guardrail in self.guardrails:
            if not _is_input(guardrail):
                raise TypeError(
                    f"guardrail {getattr(guardrail, 'name', guardrail)!r} is not an input guardrail"
                )
            outcome = guardrail.check(current_text)
            outcomes.append(outcome)
            if _STRICTNESS[outcome.decision] > _STRICTNESS[current_decision]:
                current_decision = outcome.decision
            if (
                outcome.decision is GuardrailDecision.REDACT
                and outcome.redacted_content is not None
            ):
                current_text = outcome.redacted_content
            if outcome.decision is GuardrailDecision.BLOCK:
                break
        return PipelineResult(
            decision=current_decision,
            effective_text=current_text,
            outcomes=outcomes,
        )

    def check_output(self, text: str, *, context: dict[str, str]) -> PipelineResult:
        outcomes: list[GuardrailOutcome] = []
        current_text = text
        current_decision = GuardrailDecision.PASS
        for guardrail in self.guardrails:
            if _is_input(guardrail):
                raise TypeError(
                    f"guardrail {getattr(guardrail, 'name', guardrail)!r} is not an output guardrail"
                )
            outcome = guardrail.check(current_text, context=context)
            outcomes.append(outcome)
            if _STRICTNESS[outcome.decision] > _STRICTNESS[current_decision]:
                current_decision = outcome.decision
            if (
                outcome.decision is GuardrailDecision.REDACT
                and outcome.redacted_content is not None
            ):
                current_text = outcome.redacted_content
            if outcome.decision is GuardrailDecision.BLOCK:
                break
        return PipelineResult(
            decision=current_decision,
            effective_text=current_text,
            outcomes=outcomes,
        )


def _is_input(guardrail: Any) -> bool:
    """Input guardrails have check(text) -> Outcome; output guardrails have
    check(text, *, context) -> Outcome. Inspect the signature to decide."""
    import inspect

    try:
        sig = inspect.signature(guardrail.check)
    except (TypeError, ValueError):
        return False
    # `self` is bound on the method, so we see just the other params.
    params = list(sig.parameters.values())
    return not any(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)


InputGuardrailT = InputGuardrail  # re-export alias for readability
OutputGuardrailT = OutputGuardrail
