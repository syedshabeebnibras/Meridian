"""ToolExecutor — validates + dispatches tool calls.

Flow (Section 7 §Tool invocation policy):

  1. Look up the tool in the registry (allowlist).
  2. Validate parameters against the tool's JSON schema.
  3. If the tool requires confirmation and the caller hasn't provided
     `confirmed=True`, raise NeedsConfirmationError — the orchestrator
     converts this into a user-facing confirmation prompt.
  4. Dispatch. Any exception from the tool becomes `ToolResult(status=ERROR)`
     so the orchestrator always gets a typed reply.

Call-count enforcement (max 2 per request, Section 7) lives in the caller
(the orchestrator); the executor only tracks whether *this* executor
instance has exceeded its configured cap.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from meridian_contracts import ToolInvocation, ToolResult, ToolResultStatus, ToolValidation

from meridian_tool_executor.errors import (
    InvalidParametersError,
    MaxCallsExceededError,
    NeedsConfirmationError,
)
from meridian_tool_executor.registry import ToolRegistry


@dataclass
class ToolExecutor:
    """Dispatches validated tool calls against the allowlist."""

    registry: ToolRegistry
    max_calls_per_request: int = 2
    _call_counts: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def prepare(self, invocation: ToolInvocation) -> ToolValidation:
        """Run every pre-execution check. Raises on failure so callers see
        a precise error; returns the assembled ToolValidation record on
        success so the orchestrator can attach it to audit rows.
        """
        tool = self.registry.get(invocation.tool_name)
        Draft202012Validator.check_schema(tool.schema)
        validator = Draft202012Validator(tool.schema)
        try:
            validator.validate(invocation.parameters)
        except JSONSchemaValidationError as exc:
            raise InvalidParametersError(f"{invocation.tool_name}: {exc.message}") from exc

        return ToolValidation(
            schema_valid=True,
            parameters_allowlisted=True,
            no_injection_detected=True,  # Phase 5 wires a real injection classifier
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(
        self,
        invocation: ToolInvocation,
        *,
        request_id: str,
        confirmed: bool = False,
    ) -> ToolResult:
        """Execute a validated tool call. `request_id` identifies the
        user request so we can enforce max_calls_per_request.
        """
        count = self._call_counts.get(request_id, 0)
        if count >= self.max_calls_per_request:
            raise MaxCallsExceededError(
                f"request {request_id} already made {count} tool calls; cap is "
                f"{self.max_calls_per_request}"
            )
        self._call_counts[request_id] = count + 1

        tool = self.registry.get(invocation.tool_name)
        self.prepare(invocation)  # re-validate before dispatch

        if tool.requires_confirmation and not confirmed:
            raise NeedsConfirmationError(f"{tool.name} is destructive and requires confirmation")

        started = time.perf_counter()
        try:
            result_body = tool.execute(invocation.parameters)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return ToolResult(
                tool_call_id=invocation.tool_call_id,
                tool_name=invocation.tool_name,
                status=ToolResultStatus.ERROR,
                result={},
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ToolResult(
            tool_call_id=invocation.tool_call_id,
            tool_name=invocation.tool_name,
            status=ToolResultStatus.SUCCESS,
            result=result_body,
            execution_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def reset(self, request_id: str) -> None:
        """Drop the call counter for a completed request."""
        self._call_counts.pop(request_id, None)

    @staticmethod
    def new_invocation(
        tool_name: str,
        parameters: dict[str, Any],
        *,
        requires_confirmation: bool = False,
        confirmation_message: str | None = None,
    ) -> ToolInvocation:
        """Convenience for building a ToolInvocation before validation.

        Pre-validation flag defaults are optimistic; `prepare()` overrides
        them with the real checked values.
        """
        return ToolInvocation(
            tool_call_id=f"tc_{uuid.uuid4().hex[:8]}",
            tool_name=tool_name,
            parameters=parameters,
            requires_confirmation=requires_confirmation,
            confirmation_message=confirmation_message,
            validation=ToolValidation(
                schema_valid=False,
                parameters_allowlisted=False,
                no_injection_detected=False,
            ),
        )
