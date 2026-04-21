"""Guardrail pipeline interfaces.

Concrete implementations (Presidio, Llama Guard 3, Patronus Lynx) are wired in
Phase 5. This package only exposes the Protocol classes so downstream services
can depend on the interface now without waiting for the implementations.
"""

from meridian_guardrails.interfaces import (
    GuardrailDecision,
    GuardrailOutcome,
    InputGuardrail,
    OutputGuardrail,
)

__all__ = [
    "GuardrailDecision",
    "GuardrailOutcome",
    "InputGuardrail",
    "OutputGuardrail",
]
