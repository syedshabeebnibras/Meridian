"""Slack tool — send_message (destructive / visible, requires confirmation)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx


@dataclass(frozen=True)
class SlackConfig:
    base_url: str = "https://slack.com/api"
    bot_token: str = ""
    timeout_s: float = 10.0

    @classmethod
    def from_env(cls) -> SlackConfig:
        return cls(
            base_url=os.environ.get("SLACK_BASE_URL", "https://slack.com/api"),
            bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
            timeout_s=float(os.environ.get("SLACK_TIMEOUT_S", "10.0")),
        )


def _client(config: SlackConfig, *, http: httpx.Client | None = None) -> httpx.Client:
    if http is not None:
        return http
    headers = {"Authorization": f"Bearer {config.bot_token}"} if config.bot_token else {}
    return httpx.Client(base_url=config.base_url, timeout=config.timeout_s, headers=headers)


@dataclass
class SlackSendMessageTool:
    """Posts a message to a channel. Visible to everyone in the channel —
    treat as destructive and require explicit confirmation."""

    config: SlackConfig = field(default_factory=SlackConfig.from_env)
    http: httpx.Client | None = None
    name: ClassVar[str] = "slack_send_message"
    requires_confirmation: ClassVar[bool] = True
    schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "minLength": 1},
            "text": {"type": "string", "minLength": 1, "maxLength": 4000},
            "thread_ts": {"type": "string"},
        },
        "required": ["channel", "text"],
    }

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "channel": parameters["channel"],
            "text": parameters["text"],
        }
        if parameters.get("thread_ts"):
            payload["thread_ts"] = parameters["thread_ts"]

        client = _client(self.config, http=self.http)
        response = client.post("/chat.postMessage", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"slack postMessage failed: {data.get('error', 'unknown')}")
        return {
            "channel": data["channel"],
            "ts": data["ts"],
            "permalink": (data.get("message") or {}).get("permalink", ""),
        }
