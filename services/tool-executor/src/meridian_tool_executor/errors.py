"""Executor-level exceptions. Callers catch these rather than raw tool errors."""

from __future__ import annotations


class UnknownToolError(LookupError):
    """Requested tool name is not in the registry allowlist."""


class InvalidParametersError(ValueError):
    """Parameters failed JSON-schema validation."""


class NeedsConfirmationError(RuntimeError):
    """Destructive operation called without an explicit confirmed=True."""


class MaxCallsExceededError(RuntimeError):
    """Orchestrator attempted more tool calls than the per-request cap."""
