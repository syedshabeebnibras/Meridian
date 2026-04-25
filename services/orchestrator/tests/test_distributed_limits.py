"""Phase 4 — distributed rate limiter wired into /v1/chat (legacy mode).

We exercise the legacy chat path because it lets the test build a
plain Orchestrator without a tenant DB. The rate-limit key composition
in the legacy path is ``f"{user_id}:chat"`` — a different schema from
the tenant path, but enough to verify the *shared bucket* property.

The tenant-path admin-override behaviour is unit-tested directly against
the AdminOverride dataclass.
"""

from __future__ import annotations

from typing import Any

import fakeredis
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
from meridian_ops import RedisTokenBucketRateLimiter
from meridian_orchestrator import (
    AppConfig,
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
    build_app,
)
from meridian_orchestrator.admin import AdminOverride
from meridian_orchestrator.auth import InternalAuthConfig
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry


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
                "answer": "ok",
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


def _payload(user_id: str = "userA") -> dict[str, Any]:
    return {
        "request_id": "req_phase4001",
        "user_id": user_id,
        "session_id": "sphase4",
        "query": "What's the runbook?",
        "conversation_history": [],
        "metadata": {},
    }


SECRET = "phase4-secret"


def _build_app_with(limiter, override: AdminOverride | None = None):  # type: ignore[no-untyped-def]
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    return build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
        rate_limiter=limiter,
        admin_override=override,
    )


async def test_redis_limiter_shared_across_app_instances() -> None:
    """Two FastAPI apps backed by one Redis must share one bucket."""
    server = fakeredis.FakeServer()
    limiter_a = RedisTokenBucketRateLimiter(
        redis_client=fakeredis.FakeRedis(server=server),
        capacity=2,
        refill_per_second=0.0,
        clock=lambda: 1000.0,
    )
    limiter_b = RedisTokenBucketRateLimiter(
        redis_client=fakeredis.FakeRedis(server=server),
        capacity=2,
        refill_per_second=0.0,
        clock=lambda: 1000.0,
    )
    app_a = _build_app_with(limiter_a)
    app_b = _build_app_with(limiter_b)

    headers = {"X-Internal-Key": SECRET}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_a), base_url="http://t"
    ) as client_a:
        r1 = await client_a.post("/v1/chat", json=_payload(), headers=headers)
        assert r1.status_code == 200
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_b), base_url="http://t"
    ) as client_b:
        r2 = await client_b.post("/v1/chat", json=_payload(), headers=headers)
        assert r2.status_code == 200
        # Bucket is now empty across both apps.
        r3 = await client_b.post("/v1/chat", json=_payload(), headers=headers)
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers


# ---------------------------------------------------------------------------
# AdminOverride — unit test
# ---------------------------------------------------------------------------
def test_admin_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_RATELIMIT_BYPASS_WORKSPACES", "ws1, ws2 ,ws3")
    monkeypatch.setenv("MERIDIAN_BUDGET_BYPASS_WORKSPACES", "ws1")
    override = AdminOverride.from_env()
    assert override.rate_limit_exempt("ws1")
    assert override.rate_limit_exempt("ws2")
    assert override.rate_limit_exempt("ws3")
    assert not override.rate_limit_exempt("ws4")
    assert override.budget_exempt("ws1")
    assert not override.budget_exempt("ws2")


def test_admin_override_empty_means_no_bypass() -> None:
    override = AdminOverride.from_env()
    assert not override.rate_limit_exempt("anything")
    assert not override.budget_exempt("anything")
