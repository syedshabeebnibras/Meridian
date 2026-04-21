"""Pass-through guardrail stubs used in tests and when a real service is down.

Each returns PASS with zero redaction. The orchestrator treats them as no-ops.
"""

from __future__ import annotations

from dataclasses import dataclass

from meridian_guardrails.interfaces import GuardrailDecision, GuardrailOutcome


@dataclass
class PassThroughInputGuardrail:
    name: str = "pass_through_input"

    def check(self, text: str) -> GuardrailOutcome:
        return GuardrailOutcome(decision=GuardrailDecision.PASS, reason="stub")


@dataclass
class PassThroughOutputGuardrail:
    name: str = "pass_through_output"

    def check(self, text: str, *, context: dict[str, str]) -> GuardrailOutcome:
        return GuardrailOutcome(decision=GuardrailDecision.PASS, reason="stub")
