"""Model request/response contracts — Section 8.

These are what the Model Gateway sends/receives. The shape is OpenAI-compatible
because LiteLLM normalises every provider to that schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CacheControlBreakpoint(StrEnum):
    """Explicit cache breakpoints the assembler can emit in a message."""

    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class _JsonSchemaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strict: bool = True
    schema_: dict[str, Any] = Field(alias="schema")


class ResponseFormat(BaseModel):
    """Structured output spec — Section 19 Decision notes (constrained decoding)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["json_schema", "text"]
    json_schema: _JsonSchemaSpec | None = None


class ModelRequest(BaseModel):
    """Payload sent to the Model Gateway."""

    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[_Message]
    max_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0.0, le=2.0, default=0.1)
    response_format: ResponseFormat | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(ge=0, default=0)
    cache_creation_input_tokens: int = Field(ge=0, default=0)


class ModelResponse(BaseModel):
    """Model Gateway reply. `content` is the structured output dict when
    response_format.type == "json_schema", else a free-text string."""

    model_config = ConfigDict(extra="forbid")

    id: str
    model: str
    content: dict[str, Any] | str
    usage: ModelUsage
    latency_ms: int = Field(ge=0)
