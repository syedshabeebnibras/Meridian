"""Telemetry layer — Section 11 §Instrumentation strategy.

Phase 6 ships:
  - Tracer + SpanHandle for stage-scoped spans with Section-8 attributes
  - In-memory + OTel exporters (swappable)
  - LifecycleStage enum naming every span the orchestrator emits
  - build_telemetry_event() for Section-8-compatible trace records
"""

from meridian_telemetry.semconv import GenAIAttr, MeridianAttr
from meridian_telemetry.tracer import (
    InMemoryExporter,
    LifecycleStage,
    NoOpExporter,
    OTelExporter,
    RecordedSpan,
    SpanExporter,
    SpanHandle,
    Tracer,
    build_telemetry_event,
)

__all__ = [
    "GenAIAttr",
    "InMemoryExporter",
    "LifecycleStage",
    "MeridianAttr",
    "NoOpExporter",
    "OTelExporter",
    "RecordedSpan",
    "SpanExporter",
    "SpanHandle",
    "Tracer",
    "build_telemetry_event",
]
