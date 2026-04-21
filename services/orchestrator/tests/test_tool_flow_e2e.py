"""Tool-flow end-to-end tests - Phase 4 exit criterion "tool invocations execute successfully"."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelRequest,
    ModelResponse,
    ModelTier,
    ModelUsage,
    PromptTemplate,
    TokenBudget,
    UserRequest,
)
from meridian_orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorStatus,
    TemplateProvider,
)
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry
from meridian_tool_executor import (
    JiraConfig,
    JiraCreateTicketTool,
    JiraLookupStatusTool,
    SlackConfig,
    SlackSendMessageTool,
    ToolExecutor,
    ToolRegistry,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


class FileTemplateProvider(TemplateProvider):
    def get_active(self, name: str, environment: str) -> PromptTemplate:
        path = REPO_ROOT / "prompts" / name / "v1.yaml"
        raw = yaml.safe_load(path.read_text())
        return PromptTemplate(
            name=raw["name"],
            version=1,
            model_tier=ModelTier(raw["model_tier"]),
            min_model=raw["min_model"],
            template=raw["template"],
            parameters=raw["parameters"],
            schema_ref=raw["schema_ref"],
            few_shot_dataset=raw.get("few_shot_dataset"),
            token_budget=TokenBudget.model_validate(raw["token_budget"]),
            cache_control=CacheControl.model_validate(raw["cache_control"]),
            activation=ActivationInfo(
                environment=environment,
                status=ActivationStatus.DRAFT,
                canary_percentage=0,
                activated_at=datetime.now(tz=UTC),
                activated_by="t@t.com",
            ),
        )


@dataclass
class ScriptedModel:
    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[ModelRequest] = field(default_factory=list)

    def chat(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        content = self.responses.get(request.model, {})
        return ModelResponse(
            id="stub",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


def _empty_docs() -> MockRetrievalClient:
    return MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])])


def _user_request(query: str, *, confirmed: bool = False) -> UserRequest:
    return UserRequest(
        request_id="req_tool001",
        user_id="u_bob",
        session_id="s_1",
        query=query,
        metadata={"confirmed": "yes" if confirmed else "no"},
    )


def test_jira_lookup_status_executes_without_confirmation() -> None:
    def jira_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/api/3/issue/ENG-4521"
        return httpx.Response(
            200,
            json={
                "key": "ENG-4521",
                "fields": {
                    "status": {"name": "In Progress"},
                    "assignee": {"displayName": "Alice"},
                    "updated": "2026-04-17T09:30:00.000Z",
                },
            },
        )

    http = httpx.Client(base_url="https://jira", transport=httpx.MockTransport(jira_handler))
    registry = ToolRegistry()
    registry.register(
        JiraLookupStatusTool(
            config=JiraConfig(base_url="https://jira", email="a@b", api_token="x"),
            http=http,
        )
    )
    executor = ToolExecutor(registry=registry)
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "tool_action", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "action": "call_tool",
                "tool_call": {
                    "tool_name": "jira_lookup_status",
                    "parameters": {"ticket_id": "ENG-4521"},
                    "requires_confirmation": False,
                    "confirmation_message": "",
                },
                "clarification_question": None,
                "reasoning": "read-only lookup",
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_empty_docs(),
        model_client=model,
        tool_executor=executor,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("What's the status of ENG-4521?"))
    assert reply.status is OrchestratorStatus.OK
    assert reply.tool_result is not None
    assert reply.tool_result.result["status"] == "In Progress"
    assert reply.tool_invocation is not None
    assert reply.tool_invocation.validation.schema_valid is True


def test_jira_create_ticket_pending_confirmation_then_executes() -> None:
    created_tickets: list[dict[str, Any]] = []

    def jira_handler(request: httpx.Request) -> httpx.Response:
        created_tickets.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={"key": "ENG-9000", "fields": {"created": "2026-04-20T10:00:00.000Z"}},
        )

    http = httpx.Client(base_url="https://jira", transport=httpx.MockTransport(jira_handler))
    registry = ToolRegistry()
    registry.register(
        JiraCreateTicketTool(
            config=JiraConfig(base_url="https://jira", email="a@b", api_token="x"),
            http=http,
        )
    )
    executor = ToolExecutor(registry=registry)
    tool_call = {
        "tool_name": "jira_create_ticket",
        "parameters": {
            "project": "ENG",
            "issue_type": "bug",
            "title": "Memory leak in auth service",
            "description": "OOMs after 48 hours.",
            "priority": "high",
            "labels": ["memory-leak"],
        },
        "requires_confirmation": True,
        "confirmation_message": "I'll open an ENG bug 'Memory leak in auth service'. Proceed?",
    }
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "tool_action", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "action": "call_tool",
                "tool_call": tool_call,
                "clarification_question": None,
                "reasoning": "destructive",
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_empty_docs(),
        model_client=model,
        tool_executor=executor,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("Create a Jira for the auth memory leak"))
    assert reply.status is OrchestratorStatus.PENDING_CONFIRMATION
    assert reply.tool_invocation is not None
    assert reply.tool_result is None
    assert created_tickets == []

    reply2 = orch.handle(_user_request("Create a Jira for the auth memory leak", confirmed=True))
    assert reply2.status is OrchestratorStatus.OK
    assert reply2.tool_result is not None
    assert reply2.tool_result.result["ticket_id"] == "ENG-9000"
    assert created_tickets


def test_slack_send_message_confirmation_flow() -> None:
    posts: list[dict[str, Any]] = []

    def slack_handler(request: httpx.Request) -> httpx.Response:
        posts.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"ok": True, "channel": "C_INC", "ts": "1712.0001", "message": {"permalink": ""}},
        )

    http = httpx.Client(base_url="https://slack", transport=httpx.MockTransport(slack_handler))
    registry = ToolRegistry()
    registry.register(
        SlackSendMessageTool(
            config=SlackConfig(base_url="https://slack", bot_token="botty"),
            http=http,
        )
    )
    executor = ToolExecutor(registry=registry)
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "tool_action", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "action": "call_tool",
                "tool_call": {
                    "tool_name": "slack_send_message",
                    "parameters": {"channel": "#inc-db", "text": "DB restored."},
                    "requires_confirmation": True,
                    "confirmation_message": "Post 'DB restored.' to #inc-db?",
                },
                "clarification_question": None,
                "reasoning": "visible action",
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_empty_docs(),
        model_client=model,
        tool_executor=executor,
        config=OrchestratorConfig(environment="test"),
    )
    pending = orch.handle(_user_request("Tell #inc-db the database is back"))
    assert pending.status is OrchestratorStatus.PENDING_CONFIRMATION
    assert posts == []
    final = orch.handle(_user_request("Tell #inc-db the database is back", confirmed=True))
    assert final.status is OrchestratorStatus.OK
    assert final.tool_result is not None
    assert final.tool_result.result["ts"] == "1712.0001"
    assert posts and posts[0]["text"] == "DB restored."


def test_unknown_tool_fails_validation() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry=registry)
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "tool_action", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "action": "call_tool",
                "tool_call": {
                    "tool_name": "delete_production_database",
                    "parameters": {},
                    "requires_confirmation": True,
                    "confirmation_message": "",
                },
                "clarification_question": None,
                "reasoning": "",
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_empty_docs(),
        model_client=model,
        tool_executor=executor,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("drop prod db"))
    assert reply.status is OrchestratorStatus.FAILED
    assert reply.error_message is not None
    assert "not registered" in reply.error_message


def test_tool_clarification_returned_as_ok() -> None:
    registry = ToolRegistry()
    registry.register(
        JiraLookupStatusTool(
            config=JiraConfig(base_url="https://jira", email="a@b", api_token="x"),
        )
    )
    executor = ToolExecutor(registry=registry)
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "tool_action", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "action": "clarify",
                "tool_call": None,
                "clarification_question": "Which ticket ID should I look up?",
                "reasoning": "missing ticket_id",
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_empty_docs(),
        model_client=model,
        tool_executor=executor,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("What's the status"))
    assert reply.status is OrchestratorStatus.OK
    assert reply.clarification_question == "Which ticket ID should I look up?"
    assert reply.tool_result is None
