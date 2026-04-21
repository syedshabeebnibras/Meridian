"""Tool Protocol — the shape every concrete tool must satisfy."""

from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    """One callable capability the orchestrator can invoke on behalf of the user.

    `name` is the identifier the model emits in its tool_invocation response.
    `schema` is the JSON Schema for parameters — the executor validates
    against it before calling `execute`. `requires_confirmation` gates
    destructive operations behind an explicit user OK (Section 7).
    """

    name: str
    schema: dict[str, Any]
    requires_confirmation: bool

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]: ...
