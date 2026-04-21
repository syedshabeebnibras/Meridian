"""Meridian tool executor.

Schema-validated tool execution — Section 7 §Tool invocation policy.

  - Tools live in an allowlist (`ToolRegistry`); unknown tools are rejected.
  - Every invocation is validated against the tool's JSON schema before
    execution.
  - Destructive operations (create_ticket, send_message) set
    `requires_confirmation=True`; read-only ones execute immediately.
  - Maximum 2 tool calls per request (enforced at the orchestrator level).

Phase 4 ships the framework plus Jira + Slack tools. Phase 5 can layer
input-injection checks on top (Llama Guard 3 on every parameter value).
"""

from meridian_tool_executor.errors import (
    InvalidParametersError,
    MaxCallsExceededError,
    NeedsConfirmationError,
    UnknownToolError,
)
from meridian_tool_executor.executor import ToolExecutor
from meridian_tool_executor.protocols import Tool
from meridian_tool_executor.registry import ToolRegistry
from meridian_tool_executor.tools.jira import (
    JiraConfig,
    JiraCreateTicketTool,
    JiraLookupStatusTool,
)
from meridian_tool_executor.tools.slack import SlackConfig, SlackSendMessageTool

__all__ = [
    "InvalidParametersError",
    "JiraConfig",
    "JiraCreateTicketTool",
    "JiraLookupStatusTool",
    "MaxCallsExceededError",
    "NeedsConfirmationError",
    "SlackConfig",
    "SlackSendMessageTool",
    "Tool",
    "ToolExecutor",
    "ToolRegistry",
    "UnknownToolError",
]
