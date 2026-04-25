"""Phase 3 — /debug/config exposure rules + audit lifecycle emission."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
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
)
from meridian_orchestrator import (
    AppConfig,
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
    build_app,
)
from meridian_orchestrator.audit import InMemoryAuditSink
from meridian_orchestrator.auth import InternalAuthConfig
from meridian_orchestrator.feedback import InMemoryFeedbackStore
from meridian_orchestrator.wiring import CapabilityReport
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry


# ---------------------------------------------------------------------------
# Test scaffolding (mirrors test_internal_auth.py for parity)
# ---------------------------------------------------------------------------
class _FileTemplateProvider(TemplateProvider):
    def get_active(self, name: str, environment: str) -> PromptTemplate:
        from datetime import UTC, datetime
        from pathlib import Path

        import yaml

        repo_root = Path(__file__).resolve().parents[3]
        path = repo_root / "prompts" / name / "v1.yaml"
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


class _ScriptedModel:
    def chat(self, request: ModelRequest) -> ModelResponse:
        if request.model == "meridian-small":
            content: dict[str, Any] = {
                "intent": "grounded_qa",
                "confidence": 0.95,
                "model_tier": "mid",
            }
        else:
            content = {
                "reasoning": "",
                "answer": "no relevant docs",
                "citations": [],
                "confidence": 0.8,
                "needs_escalation": False,
            }
        return ModelResponse(
            id="stub",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


def _orchestrator() -> Orchestrator:
    return Orchestrator(
        templates=_FileTemplateProvider(),
        retrieval=MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])]),
        model_client=_ScriptedModel(),
        config=OrchestratorConfig(environment="test"),
    )


SECRET = "test-internal-key-xyz"


def _payload() -> dict[str, Any]:
    return {
        "request_id": "req_phase3001",
        "user_id": "uphase3",
        "session_id": "sphase3",
        "query": "What's the runbook for incident X?",
        "conversation_history": [],
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Audit lifecycle — request.received + request.completed
# ---------------------------------------------------------------------------
@pytest.fixture()
def app_with_audit():  # type: ignore[no-untyped-def]
    sink = InMemoryAuditSink()
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
        audit_sink=sink,
        feedback_store=InMemoryFeedbackStore(),
    )
    return app, sink


async def test_audit_emits_received_and_completed(app_with_audit) -> None:  # type: ignore[no-untyped-def]
    app, sink = app_with_audit
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/v1/chat", json=_payload(), headers={"X-Internal-Key": SECRET})
    assert resp.status_code == 200

    types = [e.event_type for e in sink.events]
    assert types == ["request.received", "request.completed"]

    received, completed = sink.events
    assert received.request_id == "req_phase3001"
    assert received.user_id == "uphase3"
    assert received.session_id == "sphase3"
    assert "query_length" in received.payload

    assert completed.payload["status"] == "ok"


async def test_feedback_emits_audit_event(app_with_audit) -> None:  # type: ignore[no-untyped-def]
    app, sink = app_with_audit
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        await c.post(
            "/v1/feedback",
            json={
                "request_id": "req_phase3001",
                "user_id": "uphase3",
                "verdict": "up",
                "comment": "great answer",
            },
            headers={"X-Internal-Key": SECRET},
        )
    assert any(e.event_type == "feedback.recorded" for e in sink.events)
    fb = next(e for e in sink.events if e.event_type == "feedback.recorded")
    assert fb.payload["verdict"] == "up"
    assert fb.payload["comment_length"] == len("great answer")


# ---------------------------------------------------------------------------
# /debug/config — exposure rules
# ---------------------------------------------------------------------------
async def test_debug_config_not_registered_without_capability_report() -> None:
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/debug/config", headers={"X-Internal-Key": SECRET})
    assert resp.status_code == 404


async def test_debug_config_legacy_returns_safe_dict_in_staging() -> None:
    report = CapabilityReport(environment="staging", template_provider="file")
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
        capability_report=report,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/debug/config", headers={"X-Internal-Key": SECRET})
    assert resp.status_code == 200
    body = resp.json()
    assert body["environment"] == "staging"
    assert body["template_provider"] == "file"
    assert body["model_gateway_url"] == "redacted"


async def test_debug_config_legacy_blocked_in_production() -> None:
    report = CapabilityReport(environment="production")
    auth = InternalAuthConfig(expected_key=SECRET, environment="production", dev_mode=False)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="production"),
        auth_config=auth,
        capability_report=report,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/debug/config", headers={"X-Internal-Key": SECRET})
    # 404 — refusal phrased as "not found" so the route's existence isn't a signal.
    assert resp.status_code == 404


async def test_debug_config_requires_internal_key() -> None:
    report = CapabilityReport(environment="staging")
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
        capability_report=report,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/debug/config")
    assert resp.status_code == 401
