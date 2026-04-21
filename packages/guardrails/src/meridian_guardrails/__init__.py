"""Guardrail pipeline — Section 9 §Failure modes 5, 6, 7.

Inline middleware (Section 5). Input pipeline runs before the model sees
user content; output pipeline runs before content reaches the user.

Phase 5 ships:
  - GuardrailPipeline — chains an ordered list of guardrails
  - PassThrough stubs — CI-safe; used in the orchestrator's test suite
  - Regex PII detector — always-on baseline PII detection/redaction
  - HTTP clients for LlamaGuard + Patronus Lynx — tested via MockTransport
  - Thin adapter pattern for Presidio (team-owned deployment)
"""

from meridian_guardrails.interfaces import (
    GuardrailDecision,
    GuardrailOutcome,
    InputGuardrail,
    OutputGuardrail,
)
from meridian_guardrails.llama_guard import LlamaGuardConfig, LlamaGuardInputGuardrail
from meridian_guardrails.patronus import PatronusConfig, PatronusLynxOutputGuardrail
from meridian_guardrails.pii import RegexPIIInputGuardrail, RegexPIIOutputGuardrail
from meridian_guardrails.pipeline import GuardrailPipeline, PipelineResult
from meridian_guardrails.stubs import PassThroughInputGuardrail, PassThroughOutputGuardrail

__all__ = [
    "GuardrailDecision",
    "GuardrailOutcome",
    "GuardrailPipeline",
    "InputGuardrail",
    "LlamaGuardConfig",
    "LlamaGuardInputGuardrail",
    "OutputGuardrail",
    "PassThroughInputGuardrail",
    "PassThroughOutputGuardrail",
    "PatronusConfig",
    "PatronusLynxOutputGuardrail",
    "PipelineResult",
    "RegexPIIInputGuardrail",
    "RegexPIIOutputGuardrail",
]
