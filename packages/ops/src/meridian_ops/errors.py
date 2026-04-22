"""Error taxonomy — Section 11.

Every failure in the orchestrator is one of these typed errors carrying a
MERIDIAN-### code for log aggregation and user-visible messages.
"""

from __future__ import annotations

from typing import ClassVar


class MeridianError(RuntimeError):
    """Base class for every Meridian-internal error.

    Subclasses set ``code`` (e.g. ``MERIDIAN-003``), ``category`` (from the
    Section-11 taxonomy), and ``retryable`` (whether the orchestrator
    should attempt the corrective retry path).
    """

    code: ClassVar[str] = "MERIDIAN-000"
    category: ClassVar[str] = "system"
    retryable: ClassVar[bool] = False

    def __str__(self) -> str:
        base = super().__str__()
        return f"[{self.code}] {base}" if base else f"[{self.code}]"


class GuardrailBlockedInputError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-001"
    category: ClassVar[str] = "input"
    retryable: ClassVar[bool] = False


class ClassificationError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-002"
    category: ClassVar[str] = "classification"
    retryable: ClassVar[bool] = True


class RetrievalError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-003"
    category: ClassVar[str] = "retrieval"
    retryable: ClassVar[bool] = True


class ProviderError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-004"
    category: ClassVar[str] = "provider"
    retryable: ClassVar[bool] = True


class ProviderRateLimitedError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-005"
    category: ClassVar[str] = "provider"
    retryable: ClassVar[bool] = True


class ValidationSchemaError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-006"
    category: ClassVar[str] = "validation"
    retryable: ClassVar[bool] = True  # 1 corrective retry (Section 7)


class ValidationFaithfulnessError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-007"
    category: ClassVar[str] = "validation"
    retryable: ClassVar[bool] = False  # degrade gracefully


class GuardrailBlockedOutputError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-008"
    category: ClassVar[str] = "output"
    retryable: ClassVar[bool] = False


class ToolError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-009"
    category: ClassVar[str] = "tool"
    retryable: ClassVar[bool] = False


class TimeoutError(MeridianError):
    code: ClassVar[str] = "MERIDIAN-010"
    category: ClassVar[str] = "system"
    retryable: ClassVar[bool] = False
