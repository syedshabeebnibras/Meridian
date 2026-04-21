# Tools

Meridian can invoke a small allowlist of external tools on behalf of the user. The framework lives in `services/tool-executor/` and is wired into the orchestrator's tool-action branch (Section 7 §Tool invocation policy).

---

## Core model

```
┌──────────────────────┐        ┌──────────────────┐        ┌──────────────┐
│ tool_invocation LLM  │──────▶ │   ToolExecutor   │──────▶ │  external    │
│ (mid tier, JSON out) │ call   │  • registry      │ execute│  API (Jira,  │
└──────────────────────┘        │  • validate      │ ─────▶ │   Slack)     │
                                │  • confirm       │        └──────────────┘
                                │  • max 2 calls   │
                                └──────────────────┘
```

### Guarantees

- **Allowlisted** — `ToolRegistry.get(name)` rejects any unknown tool. Models can't invent new tool names.
- **Schema validated** — every parameter payload is validated against the tool's JSON Schema before dispatch (`jsonschema` Draft 2020-12).
- **Confirmation for destructive ops** — `requires_confirmation=True` means `ToolExecutor.execute()` raises unless `confirmed=True` is passed. The orchestrator returns `OrchestratorStatus.PENDING_CONFIRMATION` and awaits a follow-up with `metadata.confirmed=="yes"`.
- **Max 2 tool calls per request** — Section 7 cap, enforced by `ToolExecutor`.
- **Typed error paths** — every exception becomes a `ToolResult(status=ERROR)`; the orchestrator never re-raises.

---

## Built-in tools (v1)

| Tool | Destructive | Parameters | Notes |
|---|---|---|---|
| `jira_create_ticket` | ✅ | project, issue_type, title, description, priority, component, labels | Calls `POST /rest/api/3/issue` |
| `jira_lookup_status` | ❌ | ticket_id (`^[A-Z]+-\d+$`) | Calls `GET /rest/api/3/issue/{ticket_id}` |
| `slack_send_message` | ✅ | channel, text, thread_ts | Calls `POST /chat.postMessage`; channel messages are visible, so treated as destructive |

Configuration (via env):

| Tool | Config class | Env vars |
|---|---|---|
| Jira | `JiraConfig` | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_TIMEOUT_S` |
| Slack | `SlackConfig` | `SLACK_BASE_URL`, `SLACK_BOT_TOKEN`, `SLACK_TIMEOUT_S` |

Both are **awaiting real credentials** — IT/DevOps provisioning per Section 4 Dependencies. Tests use `httpx.MockTransport` to avoid hitting live APIs.

---

## Confirmation flow

```
First request:  "Create a Jira for the auth memory leak"
  → Orchestrator runs tool_invocation template
  → Model emits tool_call with requires_confirmation=true
  → Orchestrator.prepare() validates the invocation
  → Since not confirmed, returns:
        OrchestratorReply(
          status=PENDING_CONFIRMATION,
          tool_invocation=...,
          error_message="I'll open an ENG bug titled ... . Proceed?",
        )

Second request: "Create a Jira for the auth memory leak"   ← same query
                metadata.confirmed="yes"                     ← the opt-in
  → Orchestrator re-runs the flow, sees confirmed=yes → executes
  → Returns OrchestratorReply(status=OK, tool_result=...)
```

This is **stateless** — the orchestrator doesn't persist the pending call between requests. The caller (web UI, Slack bot) renders the confirmation message to the user and resends the original query with `metadata.confirmed="yes"` on approval. Session memory in Redis (Phase 6) can short-circuit the second model call once we have it.

---

## Adding a new tool

```python
from dataclasses import dataclass
from typing import Any, ClassVar

@dataclass
class GitHubCreateIssueTool:
    name: ClassVar[str] = "github_create_issue"
    requires_confirmation: ClassVar[bool] = True
    schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "repo": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["repo", "title"],
    }

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        # ... HTTP call, return a dict ...
        return {"issue_number": 42, "url": "..."}

# In orchestrator setup:
registry = ToolRegistry()
registry.register(GitHubCreateIssueTool())
```

Checklist for any new tool:
- [ ] `requires_confirmation` set correctly (destructive = True)
- [ ] JSON Schema is tight (`required`, `minLength`, enums where applicable)
- [ ] HTTP call uses the injectable `http: httpx.Client | None` pattern so tests can use `MockTransport`
- [ ] Unit test via `httpx.MockTransport`
- [ ] E2E test through the orchestrator (follow `test_tool_flow_e2e.py`)

---

## Security

Per Section 6 §Prompt injection resistance:

1. **Tool parameters are validated against a JSON schema** — no free-form strings slip through as code.
2. **Tool allowlist** — unknown tool names are rejected at `ToolRegistry.get()`.
3. **Retrieved documents are treated as data**, not instructions — the tool_invocation template explicitly says so.
4. **Destructive ops require explicit user confirmation** — the orchestrator cannot bypass this.

Phase 5 adds a Llama Guard 3 injection classifier on every parameter value; `ToolValidation.no_injection_detected` is currently hard-coded to `True` and will be wired to the real classifier then.
