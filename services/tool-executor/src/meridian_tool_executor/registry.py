"""ToolRegistry — allowlist of known tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from meridian_tool_executor.errors import UnknownToolError
from meridian_tool_executor.protocols import Tool


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownToolError(f"tool {name!r} is not registered") from exc

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools
