"""Jira + Slack tool tests using httpx.MockTransport — no credentials needed."""

from __future__ import annotations

import json

import httpx
from meridian_tool_executor import (
    JiraConfig,
    JiraCreateTicketTool,
    JiraLookupStatusTool,
    SlackConfig,
    SlackSendMessageTool,
)


def test_jira_create_ticket_posts_issue_and_returns_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/api/3/issue"
        body = json.loads(request.content)
        assert body["fields"]["summary"] == "Auth service memory leak"
        assert body["fields"]["project"] == {"key": "ENG"}
        assert body["fields"]["priority"] == {"name": "High"}
        return httpx.Response(
            201,
            json={
                "key": "ENG-4521",
                "fields": {"created": "2026-04-16T10:01:00.000Z"},
            },
        )

    http = httpx.Client(base_url="https://jira", transport=httpx.MockTransport(handler))
    tool = JiraCreateTicketTool(
        config=JiraConfig(base_url="https://jira", email="a@b", api_token="x"),
        http=http,
    )
    result = tool.execute(
        {
            "project": "ENG",
            "issue_type": "bug",
            "title": "Auth service memory leak",
            "description": "Memory leak in session handler.",
            "priority": "high",
            "labels": ["memory-leak"],
        }
    )
    assert result["ticket_id"] == "ENG-4521"
    assert result["ticket_url"] == "https://jira/browse/ENG-4521"
    assert tool.requires_confirmation is True


def test_jira_lookup_status_returns_normalized_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
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

    http = httpx.Client(base_url="https://jira", transport=httpx.MockTransport(handler))
    tool = JiraLookupStatusTool(
        config=JiraConfig(base_url="https://jira", email="a@b", api_token="x"),
        http=http,
    )
    result = tool.execute({"ticket_id": "ENG-4521"})
    assert result["status"] == "In Progress"
    assert result["assignee"] == "Alice"
    assert tool.requires_confirmation is False


def test_slack_send_message_hits_chat_postmessage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "ok": True,
                "channel": "C0123456",
                "ts": "1712345678.000100",
                "message": {"permalink": "https://slack.example/x"},
            },
        )

    http = httpx.Client(
        base_url="https://slack",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer botty"},
    )
    tool = SlackSendMessageTool(
        config=SlackConfig(base_url="https://slack", bot_token="botty"),
        http=http,
    )
    result = tool.execute({"channel": "#ops", "text": "Ack on P1."})
    assert captured["url"] == "/chat.postMessage"
    assert result["ts"] == "1712345678.000100"
    assert tool.requires_confirmation is True


def test_slack_send_message_raises_when_api_returns_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})

    http = httpx.Client(base_url="https://slack", transport=httpx.MockTransport(handler))
    tool = SlackSendMessageTool(config=SlackConfig(base_url="https://slack"), http=http)

    try:
        tool.execute({"channel": "#missing", "text": "hi"})
    except RuntimeError as exc:
        assert "channel_not_found" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
