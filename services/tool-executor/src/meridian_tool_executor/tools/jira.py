"""Jira tools — create_ticket (destructive) + lookup_status (read-only).

Both hit the Atlassian REST API v3. Tests inject an httpx.MockTransport so
no credentials are needed in CI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx


@dataclass(frozen=True)
class JiraConfig:
    base_url: str = "https://company.atlassian.net"
    email: str = ""
    api_token: str = ""
    timeout_s: float = 10.0  # Section 7 §Timeouts — tool execution budget

    @classmethod
    def from_env(cls) -> JiraConfig:
        return cls(
            base_url=os.environ.get("JIRA_BASE_URL", "https://company.atlassian.net"),
            email=os.environ.get("JIRA_EMAIL", ""),
            api_token=os.environ.get("JIRA_API_TOKEN", ""),
            timeout_s=float(os.environ.get("JIRA_TIMEOUT_S", "10.0")),
        )


def _client(config: JiraConfig, *, http: httpx.Client | None = None) -> httpx.Client:
    if http is not None:
        return http
    auth: httpx.BasicAuth | None = None
    if config.email and config.api_token:
        auth = httpx.BasicAuth(username=config.email, password=config.api_token)
    return httpx.Client(base_url=config.base_url, timeout=config.timeout_s, auth=auth)


@dataclass
class JiraCreateTicketTool:
    """Creates a Jira issue. Destructive — requires user confirmation."""

    config: JiraConfig = field(default_factory=JiraConfig.from_env)
    http: httpx.Client | None = None
    name: ClassVar[str] = "jira_create_ticket"
    requires_confirmation: ClassVar[bool] = True
    schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "project": {"type": "string", "minLength": 1},
            "issue_type": {
                "type": "string",
                "enum": ["bug", "task", "story", "incident"],
            },
            "title": {"type": "string", "minLength": 1, "maxLength": 255},
            "description": {"type": "string"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
            },
            "component": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["project", "issue_type", "title"],
    }

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        body = {
            "fields": {
                "project": {"key": parameters["project"]},
                "issuetype": {"name": parameters["issue_type"].capitalize()},
                "summary": parameters["title"],
                "description": parameters.get("description", ""),
                "priority": {"name": parameters.get("priority", "medium").capitalize()},
                "labels": parameters.get("labels", []),
            }
        }
        component = parameters.get("component")
        if component:
            body["fields"]["components"] = [{"name": component}]

        client = _client(self.config, http=self.http)
        response = client.post("/rest/api/3/issue", json=body)
        response.raise_for_status()
        data = response.json()
        ticket_id = data["key"]
        return {
            "ticket_id": ticket_id,
            "ticket_url": f"{self.config.base_url}/browse/{ticket_id}",
            "created_at": data.get("fields", {}).get("created", ""),
        }


@dataclass
class JiraLookupStatusTool:
    """Looks up the current status of a Jira issue. Read-only."""

    config: JiraConfig = field(default_factory=JiraConfig.from_env)
    http: httpx.Client | None = None
    name: ClassVar[str] = "jira_lookup_status"
    requires_confirmation: ClassVar[bool] = False
    schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "pattern": r"^[A-Z]+-\d+$"},
        },
        "required": ["ticket_id"],
    }

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        ticket_id = parameters["ticket_id"]
        client = _client(self.config, http=self.http)
        response = client.get(f"/rest/api/3/issue/{ticket_id}")
        response.raise_for_status()
        data = response.json()
        fields = data.get("fields", {})
        return {
            "ticket_id": data.get("key", ticket_id),
            "ticket_url": f"{self.config.base_url}/browse/{ticket_id}",
            "status": fields.get("status", {}).get("name", "unknown"),
            "assignee": (fields.get("assignee") or {}).get("displayName", "unassigned"),
            "updated_at": fields.get("updated", ""),
        }
