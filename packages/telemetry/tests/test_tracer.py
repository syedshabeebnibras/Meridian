"""Tracer + exporter tests."""

from __future__ import annotations

import pytest
from meridian_contracts import TelemetryStatus
from meridian_telemetry import (
    InMemoryExporter,
    LifecycleStage,
    NoOpExporter,
    Tracer,
    build_telemetry_event,
)


def test_span_records_attributes_and_duration() -> None:
    exporter = InMemoryExporter()
    tracer = Tracer(exporter=exporter)
    with tracer.span(
        LifecycleStage.CLASSIFICATION,
        attributes={"meridian.intent": "grounded_qa"},
    ) as handle:
        handle.set_attribute("gen_ai.request.model", "meridian-small")

    assert len(exporter.spans) == 1
    span = exporter.spans[0]
    assert span.operation == "meridian.classification"
    assert span.attributes["meridian.intent"] == "grounded_qa"
    assert span.attributes["gen_ai.request.model"] == "meridian-small"
    assert span.status is TelemetryStatus.OK
    assert span.duration_ms >= 0
    assert span.trace_id.startswith("tr_")
    assert span.span_id.startswith("sp_")


def test_parent_child_share_trace_id() -> None:
    exporter = InMemoryExporter()
    tracer = Tracer(exporter=exporter)
    with (
        tracer.span(LifecycleStage.REQUEST) as parent,
        tracer.span(LifecycleStage.RETRIEVAL, parent=parent) as child,
    ):
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id
        assert child.span_id != parent.span_id


def test_span_records_error_on_exception() -> None:
    exporter = InMemoryExporter()
    tracer = Tracer(exporter=exporter)
    with pytest.raises(RuntimeError), tracer.span(LifecycleStage.MODEL_DISPATCH):
        raise RuntimeError("boom")

    span = exporter.spans[-1]
    assert span.status is TelemetryStatus.ERROR
    assert "RuntimeError" in span.attributes["error.message"]


def test_noop_exporter_is_the_default() -> None:
    tracer = Tracer()
    assert isinstance(tracer.exporter, NoOpExporter)
    # Should not raise and should not retain anything.
    with tracer.span(LifecycleStage.REQUEST):
        pass


def test_in_memory_exporter_by_name() -> None:
    exporter = InMemoryExporter()
    tracer = Tracer(exporter=exporter)
    with tracer.span(LifecycleStage.INPUT_GUARDRAILS):
        pass
    with tracer.span(LifecycleStage.INPUT_GUARDRAILS):
        pass
    with tracer.span(LifecycleStage.RETRIEVAL):
        pass

    assert len(exporter.by_name("meridian.input_guardrails")) == 2
    assert len(exporter.by_name("meridian.retrieval")) == 1
    exporter.clear()
    assert exporter.spans == []


def test_build_telemetry_event_matches_section_8() -> None:
    exporter = InMemoryExporter()
    tracer = Tracer(exporter=exporter)
    with tracer.span(LifecycleStage.MODEL_DISPATCH) as handle:
        handle.set_attributes(
            {
                "gen_ai.system": "anthropic",
                "gen_ai.request.model": "meridian-mid",
                "gen_ai.usage.input_tokens": 1200,
                "gen_ai.usage.output_tokens": 300,
                "meridian.cost_usd": 0.012,
            }
        )

    event = build_telemetry_event(exporter.spans[0])
    assert event.operation == "meridian.model_dispatch"
    assert event.attributes["gen_ai.system"] == "anthropic"
    assert event.attributes["gen_ai.usage.input_tokens"] == 1200
    assert event.service == "meridian-orchestrator"
    assert event.status is TelemetryStatus.OK
