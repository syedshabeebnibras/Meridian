"""ToolExecutor tests — allowlist + schema + confirmation + call cap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from meridian_contracts import ToolInvocation, ToolResultStatus, ToolValidation
from meridian_tool_executor import (
    InvalidParametersError,
    MaxCallsExceededError,
    NeedsConfirmationError,
    Tool,
    ToolExecutor,
    ToolRegistry,
    UnknownToolError,
)


@dataclass
class FakeTool:
    name: str = "echo"
    schema: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        }
    )
    requires_confirmation: bool = False
    should_raise: bool = False

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        if self.should_raise:
            raise RuntimeError("boom")
        return {"echo": parameters["msg"]}


def _invocation(tool_name: str, parameters: dict[str, Any]) -> ToolInvocation:
    return ToolInvocation(
        tool_call_id="tc_test",
        tool_name=tool_name,
        parameters=parameters,
        requires_confirmation=False,
        validation=ToolValidation(
            schema_valid=False,
            parameters_allowlisted=False,
            no_injection_detected=False,
        ),
    )


def _executor(*tools: Tool, max_calls: int = 2) -> ToolExecutor:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return ToolExecutor(registry=registry, max_calls_per_request=max_calls)


def test_unknown_tool_rejected() -> None:
    executor = _executor(FakeTool())
    with pytest.raises(UnknownToolError):
        executor.execute(_invocation("nope", {"msg": "hi"}), request_id="r1")


def test_schema_validation_rejects_missing_required() -> None:
    executor = _executor(FakeTool())
    with pytest.raises(InvalidParametersError):
        executor.execute(_invocation("echo", {}), request_id="r1")


def test_happy_path_returns_success_result() -> None:
    executor = _executor(FakeTool())
    result = executor.execute(_invocation("echo", {"msg": "hi"}), request_id="r1")
    assert result.status is ToolResultStatus.SUCCESS
    assert result.result == {"echo": "hi"}


def test_destructive_tool_requires_confirmation() -> None:
    tool = FakeTool(name="delete_everything", requires_confirmation=True)
    executor = _executor(tool)
    with pytest.raises(NeedsConfirmationError):
        executor.execute(_invocation("delete_everything", {"msg": "ok"}), request_id="r1")
    # With confirmed=True it runs.
    result = executor.execute(
        _invocation("delete_everything", {"msg": "ok"}),
        request_id="r2",
        confirmed=True,
    )
    assert result.status is ToolResultStatus.SUCCESS


def test_tool_error_is_captured_not_raised() -> None:
    tool = FakeTool(should_raise=True)
    executor = _executor(tool)
    result = executor.execute(_invocation("echo", {"msg": "hi"}), request_id="r1")
    assert result.status is ToolResultStatus.ERROR
    assert result.error == "boom"


def test_max_calls_cap_enforced_per_request() -> None:
    executor = _executor(FakeTool(), max_calls=2)
    executor.execute(_invocation("echo", {"msg": "1"}), request_id="r1")
    executor.execute(_invocation("echo", {"msg": "2"}), request_id="r1")
    with pytest.raises(MaxCallsExceededError):
        executor.execute(_invocation("echo", {"msg": "3"}), request_id="r1")
    # Different request_id starts fresh.
    executor.execute(_invocation("echo", {"msg": "r2"}), request_id="r2")


def test_reset_clears_the_per_request_counter() -> None:
    executor = _executor(FakeTool(), max_calls=1)
    executor.execute(_invocation("echo", {"msg": "1"}), request_id="r1")
    with pytest.raises(MaxCallsExceededError):
        executor.execute(_invocation("echo", {"msg": "2"}), request_id="r1")
    executor.reset("r1")
    executor.execute(_invocation("echo", {"msg": "again"}), request_id="r1")


def test_prepare_returns_validation_record() -> None:
    executor = _executor(FakeTool())
    validation = executor.prepare(_invocation("echo", {"msg": "hi"}))
    assert validation.schema_valid is True
    assert validation.parameters_allowlisted is True
