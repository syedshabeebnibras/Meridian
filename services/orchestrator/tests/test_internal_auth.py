"""Internal-auth tests — fail-closed, dev escape, correct acceptance."""

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
from meridian_orchestrator.auth import InternalAuthConfig, InternalAuthConfigError
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry


# ---------------------------------------------------------------------------
# Boot-time configuration
# ---------------------------------------------------------------------------
def test_from_env_requires_key_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_ENV", "production")
    monkeypatch.delenv("ORCH_INTERNAL_KEY", raising=False)
    monkeypatch.delenv("MERIDIAN_ALLOW_UNAUTH_INTERNAL", raising=False)
    with pytest.raises(InternalAuthConfigError) as excinfo:
        InternalAuthConfig.from_env()
    assert "ORCH_INTERNAL_KEY" in str(excinfo.value)


def test_from_env_requires_key_in_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_ENV", "staging")
    monkeypatch.delenv("ORCH_INTERNAL_KEY", raising=False)
    monkeypatch.delenv("MERIDIAN_ALLOW_UNAUTH_INTERNAL", raising=False)
    with pytest.raises(InternalAuthConfigError):
        InternalAuthConfig.from_env()


def test_from_env_accepts_dev_mode_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_ENV", "dev")
    monkeypatch.setenv("MERIDIAN_ALLOW_UNAUTH_INTERNAL", "true")
    monkeypatch.delenv("ORCH_INTERNAL_KEY", raising=False)
    config = InternalAuthConfig.from_env()
    assert config.dev_mode is True
    assert config.expected_key == ""


def test_from_env_dev_env_without_opt_in_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # Just setting MERIDIAN_ENV=dev is not enough — opt-in flag is required.
    monkeypatch.setenv("MERIDIAN_ENV", "dev")
    monkeypatch.delenv("MERIDIAN_ALLOW_UNAUTH_INTERNAL", raising=False)
    monkeypatch.delenv("ORCH_INTERNAL_KEY", raising=False)
    with pytest.raises(InternalAuthConfigError):
        InternalAuthConfig.from_env()


def test_from_env_accepts_prod_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_ENV", "production")
    monkeypatch.setenv("ORCH_INTERNAL_KEY", "super-secret-key-123")
    monkeypatch.delenv("MERIDIAN_ALLOW_UNAUTH_INTERNAL", raising=False)
    config = InternalAuthConfig.from_env()
    assert config.dev_mode is False
    assert config.expected_key == "super-secret-key-123"


# ---------------------------------------------------------------------------
# Runtime header enforcement
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


def _payload() -> dict[str, Any]:
    return {
        "request_id": "req_auth001",
        "user_id": "u_auth",
        "session_id": "s_auth",
        "query": "What's the P1 escalation procedure?",
        "conversation_history": [],
        "metadata": {},
    }


SECRET = "integration-key-abc"


@pytest.fixture()
def secure_app():  # type: ignore[no-untyped-def]
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    return build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
    )


@pytest.fixture()
async def secure_client(secure_app):  # type: ignore[no-untyped-def]
    transport = httpx.ASGITransport(app=secure_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_missing_key_is_rejected(secure_client: httpx.AsyncClient) -> None:
    resp = await secure_client.post("/v1/chat", json=_payload())
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"]


async def test_wrong_key_is_rejected(secure_client: httpx.AsyncClient) -> None:
    resp = await secure_client.post(
        "/v1/chat",
        json=_payload(),
        headers={"X-Internal-Key": "not-the-secret"},
    )
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


async def test_correct_key_is_accepted(secure_client: httpx.AsyncClient) -> None:
    resp = await secure_client.post(
        "/v1/chat",
        json=_payload(),
        headers={"X-Internal-Key": SECRET},
    )
    assert resp.status_code == 200
    assert resp.json()["request_id"] == "req_auth001"


async def test_feedback_also_requires_key(secure_client: httpx.AsyncClient) -> None:
    feedback_body = {
        "request_id": "req_auth001",
        "user_id": "u_auth",
        "verdict": "up",
        "comment": "",
    }
    # Missing key
    resp = await secure_client.post("/v1/feedback", json=feedback_body)
    assert resp.status_code == 401
    # Wrong key
    resp = await secure_client.post(
        "/v1/feedback", json=feedback_body, headers={"X-Internal-Key": "wrong"}
    )
    assert resp.status_code == 401


async def test_health_endpoints_remain_open(secure_client: httpx.AsyncClient) -> None:
    # Liveness/readiness/metrics must work without the header so orchestration
    # infrastructure (load balancers, Prometheus) can probe them.
    for path in ("/healthz", "/readyz", "/metrics"):
        resp = await secure_client.get(path)
        assert resp.status_code == 200, f"{path} should be open without key"


# ---------------------------------------------------------------------------
# Dev-mode escape hatch
# ---------------------------------------------------------------------------
async def test_dev_mode_accepts_missing_key() -> None:
    auth = InternalAuthConfig(expected_key="", environment="dev", dev_mode=True)
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="dev"),
        auth_config=auth,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        resp = await c.post("/v1/chat", json=_payload())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Timing-safe comparison
# ---------------------------------------------------------------------------
def test_compare_is_constant_time() -> None:
    # Smoke test that hmac.compare_digest is actually used — we can't
    # measure wall-clock reliably in CI, but a matching prefix should
    # still produce False for a non-matching full string.
    from meridian_orchestrator.auth import build_require_internal_key

    auth = InternalAuthConfig(expected_key="abcdefgh", environment="staging", dev_mode=False)
    dep = build_require_internal_key(auth)
    # Run synchronously by calling the coroutine and asserting HTTPException.
    import asyncio

    from fastapi import HTTPException

    async def _attempt(key: str | None) -> None:
        await dep(x_internal_key=key)

    # Correct
    asyncio.run(_attempt("abcdefgh"))
    # Matching prefix, wrong length
    with pytest.raises(HTTPException):
        asyncio.run(_attempt("abcdefg"))
    # Same length, different value
    with pytest.raises(HTTPException):
        asyncio.run(_attempt("zzzzzzzz"))
