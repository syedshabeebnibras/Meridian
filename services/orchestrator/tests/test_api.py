"""FastAPI app tests — health/readiness/metrics/chat via httpx.ASGITransport."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
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
)
from meridian_orchestrator import (
    AppConfig,
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
    build_app,
)
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry

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

    def chat(self, request: ModelRequest) -> ModelResponse:
        content = self.responses.get(request.model, {})
        return ModelResponse(
            id="stub",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


def _orchestrator() -> Orchestrator:
    return Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=MockRetrievalClient(
            fixtures=[
                FixtureEntry(
                    match="P1",
                    chunks=[],
                ),
                FixtureEntry(match="", chunks=[]),
            ]
        ),
        model_client=ScriptedModel(
            responses={
                "meridian-small": {
                    "intent": "grounded_qa",
                    "confidence": 0.95,
                    "model_tier": "mid",
                },
                "meridian-mid": {
                    "reasoning": "",
                    "answer": "no relevant docs",
                    "citations": [],
                    "confidence": 0.8,
                    "needs_escalation": False,
                },
            }
        ),
        config=OrchestratorConfig(environment="test"),
    )


@pytest.fixture()
def app():  # type: ignore[no-untyped-def]
    return build_app(_orchestrator(), config=AppConfig(environment="test"))


@pytest.fixture()
async def client(app):  # type: ignore[no-untyped-def]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_healthz_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"


async def test_readyz_returns_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.text == "ready"


async def test_readyz_returns_503_when_readiness_check_fails() -> None:
    app = build_app(_orchestrator(), readiness_check=lambda: False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        response = await c.get("/readyz")
        assert response.status_code == 503


async def test_metrics_returns_prometheus_format(client: httpx.AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "meridian_requests_total" in response.text
    assert "# HELP" in response.text


async def test_chat_returns_429_when_rate_limit_exceeded() -> None:
    """A user over the burst capacity gets 429 with Retry-After — orchestrator
    is never invoked so we don't burn compute on throttled traffic."""
    from meridian_ops import TokenBucketRateLimiter

    # capacity=1 → 2nd call trips the limiter.
    limiter = TokenBucketRateLimiter(capacity=1.0, refill_per_second=0.0)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="test"),
        rate_limiter=limiter,
    )
    transport = httpx.ASGITransport(app=app)
    payload = {
        "request_id": "req_rl001",
        "user_id": "u_ratelimit",
        "session_id": "s",
        "query": "P1 outage?",
        "conversation_history": [],
        "metadata": {},
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        first = await c.post("/v1/chat", json=payload)
        assert first.status_code == 200

        second = await c.post(
            "/v1/chat", json={**payload, "request_id": "req_rl002"}
        )
        assert second.status_code == 429
        assert second.headers.get("retry-after") == "1"


async def test_chat_returns_orchestrator_reply(client: httpx.AsyncClient) -> None:
    payload = {
        "request_id": "req_api001",
        "user_id": "u",
        "session_id": "s",
        "query": "What's the P1 escalation procedure?",
        "conversation_history": [],
        "metadata": {},
    }
    response = await client.post("/v1/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req_api001"
    assert body["status"] in (
        "ok",
        "refused",
        "failed",
        "blocked",
        "degraded",
        "pending_confirmation",
    )
    assert "orchestration_state" in body
