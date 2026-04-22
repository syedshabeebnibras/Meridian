"""Tracer — thin layer over the span attributes the rest of the codebase emits.

We don't force every service to pull in `opentelemetry-sdk` just to get
working telemetry. The Tracer is a Protocol-driven context manager that
accepts any SpanExporter:

  - InMemoryExporter  — tests (captures spans for assertions)
  - NoOpExporter      — default when telemetry is off
  - OTelExporter      — wraps opentelemetry-sdk for real prod export

Every span is stored as a RecordedSpan with Section-8 TelemetryEvent shape
so `build_telemetry_event()` can turn it into a Section-8 contract.
"""

from __future__ import annotations

import contextlib
import secrets
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC
from enum import StrEnum
from typing import Any, Protocol

from meridian_contracts import TelemetryEvent, TelemetryStatus

from meridian_telemetry.semconv import GenAIAttr, MeridianAttr  # noqa: F401


class LifecycleStage(StrEnum):
    """Meridian's request-lifecycle span names (Section 11)."""

    REQUEST = "meridian.request"
    INPUT_GUARDRAILS = "meridian.input_guardrails"
    CLASSIFICATION = "meridian.classification"
    RETRIEVAL = "meridian.retrieval"
    PROMPT_ASSEMBLY = "meridian.prompt_assembly"
    MODEL_DISPATCH = "meridian.model_dispatch"
    OUTPUT_VALIDATION = "meridian.output_validation"
    OUTPUT_GUARDRAILS = "meridian.output_guardrails"
    RESPONSE_SHAPING = "meridian.response_shaping"
    TOOL_EXECUTION = "meridian.tool_execution"


@dataclass
class RecordedSpan:
    """One completed span. Carries enough to rebuild a TelemetryEvent."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    operation: str
    started_at: float  # unix seconds
    duration_ms: int
    attributes: dict[str, Any] = field(default_factory=dict)
    status: TelemetryStatus = TelemetryStatus.OK


class SpanExporter(Protocol):
    """Anything that accepts completed spans."""

    def export(self, span: RecordedSpan) -> None: ...


class NoOpExporter:
    """Default when telemetry is turned off."""

    def export(self, span: RecordedSpan) -> None:
        return None


@dataclass
class InMemoryExporter:
    """Captures spans for test assertions."""

    spans: list[RecordedSpan] = field(default_factory=list)

    def export(self, span: RecordedSpan) -> None:
        self.spans.append(span)

    def by_name(self, name: str) -> list[RecordedSpan]:
        return [s for s in self.spans if s.operation == name]

    def clear(self) -> None:
        self.spans.clear()


class OTelExporter:
    """Wraps opentelemetry-sdk. Imported lazily so `import meridian_telemetry`
    never pulls the SDK unless the caller actually uses it."""

    def __init__(self, service_name: str = "meridian-orchestrator") -> None:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        self._otel_trace = trace
        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self._provider)
        self._tracer = trace.get_tracer(service_name)

    def export(self, span: RecordedSpan) -> None:
        # Emit a one-shot span via the SDK. For long-running integrations
        # the caller is expected to open real otel spans instead — this
        # exporter is a bridge for the simple in-process tracer.
        with self._tracer.start_as_current_span(
            span.operation,
            attributes=_flatten_attrs(span.attributes),
        ):
            pass


def _flatten_attrs(attributes: dict[str, Any]) -> dict[str, Any]:
    """OTel accepts a limited set of attribute value types; coerce here."""
    flat: dict[str, Any] = {}
    for k, v in attributes.items():
        if isinstance(v, (str, int, float, bool)):
            flat[k] = v
        elif v is None:
            continue
        else:
            flat[k] = str(v)
    return flat


@dataclass
class SpanHandle:
    """Live span — the tracer context manager yields this."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation: str
    started_at: float
    _attributes: dict[str, Any] = field(default_factory=dict)
    _status: TelemetryStatus = TelemetryStatus.OK
    _clock: Callable[[], float] = time.perf_counter

    def set_attribute(self, key: str, value: Any) -> None:
        self._attributes[key] = value

    def set_attributes(self, attrs: dict[str, Any]) -> None:
        self._attributes.update(attrs)

    def set_error(self, reason: str) -> None:
        self._status = TelemetryStatus.ERROR
        self._attributes["error.message"] = reason


@dataclass
class Tracer:
    """Stage-scoped tracer. Every service takes one of these and opens spans."""

    service: str = "meridian-orchestrator"
    exporter: SpanExporter = field(default_factory=NoOpExporter)
    clock: Callable[[], float] = time.perf_counter
    wallclock: Callable[[], float] = time.time

    @contextlib.contextmanager
    def span(
        self,
        name: str | LifecycleStage,
        *,
        trace_id: str | None = None,
        parent: SpanHandle | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[SpanHandle]:
        op = name.value if isinstance(name, LifecycleStage) else name
        active_trace_id = trace_id or (parent.trace_id if parent else _new_trace_id())
        span_id = _new_span_id()
        parent_id = parent.span_id if parent else None
        handle = SpanHandle(
            trace_id=active_trace_id,
            span_id=span_id,
            parent_span_id=parent_id,
            operation=op,
            started_at=self.wallclock(),
            _attributes=dict(attributes or {}),
            _clock=self.clock,
        )
        perf_started = self.clock()
        try:
            yield handle
        except Exception as exc:
            handle.set_error(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            duration_ms = max(0, int((self.clock() - perf_started) * 1000))
            self.exporter.export(
                RecordedSpan(
                    trace_id=handle.trace_id,
                    span_id=handle.span_id,
                    parent_span_id=handle.parent_span_id,
                    service=self.service,
                    operation=handle.operation,
                    started_at=handle.started_at,
                    duration_ms=duration_ms,
                    attributes=dict(handle._attributes),
                    status=handle._status,
                )
            )


def _new_trace_id() -> str:
    return f"tr_{secrets.token_hex(16)}"


def _new_span_id() -> str:
    return f"sp_{uuid.uuid4().hex[:12]}"


def build_telemetry_event(span: RecordedSpan) -> TelemetryEvent:
    """Turn a RecordedSpan into the Section-8 TelemetryEvent contract."""
    from datetime import datetime

    return TelemetryEvent(
        trace_id=span.trace_id,
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        service=span.service,
        operation=span.operation,
        timestamp=datetime.fromtimestamp(span.started_at, tz=UTC),
        duration_ms=span.duration_ms,
        attributes=span.attributes,
        status=span.status,
    )
