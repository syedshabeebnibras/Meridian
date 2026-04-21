"""Telemetry event contract — Section 8.

OTel-compatible span record. Attribute keys use the GenAI semantic conventions
plus Meridian-specific extensions (both defined in meridian_telemetry.semconv).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelemetryStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    service: str
    operation: str
    timestamp: datetime
    duration_ms: int = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: TelemetryStatus = TelemetryStatus.OK
