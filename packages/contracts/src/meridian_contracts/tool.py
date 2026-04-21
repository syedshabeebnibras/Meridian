"""Tool invocation and tool result contracts — Section 8.

Tool calls are synchronous in v1 (Section 19 Decision 7) and run through the
tool executor with allowlisted parameter validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    TIMEOUT = "timeout"


class ToolValidation(BaseModel):
    """Pre-execution checks that must all pass before the call is dispatched."""

    model_config = ConfigDict(extra="forbid")

    schema_valid: bool
    parameters_allowlisted: bool
    no_injection_detected: bool


class ToolInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    tool_name: str
    parameters: dict[str, Any]
    requires_confirmation: bool = False
    confirmation_message: str | None = None
    validation: ToolValidation


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    tool_name: str
    status: ToolResultStatus
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    execution_time_ms: int = Field(ge=0)
