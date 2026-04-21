"""User request contract — Section 8.

Inbound payload from the API gateway to the orchestrator.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationTurn(BaseModel):
    """One turn of prior conversation, surfaced to the orchestrator for in-session memory."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime


class UserRequest(BaseModel):
    """Inbound request from the API gateway. Shape matches Section 8 exactly."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^req_[a-zA-Z0-9]+$")
    user_id: str
    session_id: str
    query: str = Field(min_length=1)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
