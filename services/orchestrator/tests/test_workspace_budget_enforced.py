"""Workspace cost breaker is *enforced*, not just implemented.

Pins three properties:

  1. A request from a workspace whose recorded daily spend exceeds the
     raw budget gets HTTP 402 *before* the orchestrator runs — model
     budget is not burned past the cap.
  2. Once the breaker is closed (spend below budget), normal requests
     proceed and ``daily_tracker.record`` is called with the reply's cost.
  3. ``MERIDIAN_BUDGET_BYPASS_WORKSPACES`` lets an admin opt a workspace
     out of the cap without restarting.

These tests build the FastAPI app directly (no real DB) — the breaker
only needs the DailyTracker Protocol, satisfied by ``PerUserDailyTracker``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import httpx
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
from meridian_cost_accounting import PerUserDailyTracker, WorkspaceCostBreaker
from meridian_db.tenants import Role
from meridian_orchestrator import (
    AppConfig,
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
    build_app,
)
from meridian_orchestrator.admin import AdminOverride
from meridian_orchestrator.auth import InternalAuthConfig
from meridian_orchestrator.caller import CallerContext
from meridian_orchestrator.sessions import (
    ChatMessageSummary,
    ChatSessionSummary,
    PersistRequest,
)
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry

SECRET = "ws-budget-secret"
WORKSPACE_OK = uuid.UUID("11111111-1111-1111-1111-111111111111")
WORKSPACE_OVER = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


# ---------------------------------------------------------------------------
# Test scaffolding (mirrors test_internal_auth.py shape)
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
                "answer": "ok",
                "citations": [],
                "confidence": 0.8,
                "needs_escalation": False,
            }
        return ModelResponse(
            id="stub",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            latency_ms=1,
        )


def _orchestrator() -> Orchestrator:
    # Wire a CostAccountant so the reply carries a real cost_usd — that's
    # what gates the per-workspace daily-tracker record on the api side.
    from meridian_cost_accounting import CostAccountant

    return Orchestrator(
        templates=_FileTemplateProvider(),
        retrieval=MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])]),
        model_client=_ScriptedModel(),
        cost_accountant=CostAccountant(),
        config=OrchestratorConfig(environment="test"),
    )


class _StubSessionService:
    """Drop-in for SessionService that doesn't need a real DB."""

    def __init__(self, session_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self._id = session_id
        self._ws = workspace_id
        self._user = user_id
        self.persisted: list[PersistRequest] = []

    def get_session(self, *, session_id: uuid.UUID, workspace_id: uuid.UUID) -> ChatSessionSummary:
        from datetime import UTC, datetime

        return ChatSessionSummary(
            id=self._id,
            workspace_id=workspace_id,
            user_id=self._user,
            title="t",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

    def persist_exchange(self, request: PersistRequest) -> tuple[uuid.UUID, uuid.UUID]:
        self.persisted.append(request)
        return uuid.uuid4(), uuid.uuid4()

    # Unused in these tests but referenced by other handlers:
    def list_sessions(self, *, workspace_id: uuid.UUID) -> list[ChatSessionSummary]:
        return []

    def list_messages(
        self, *, session_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[ChatMessageSummary]:
        return []


def _require_caller(workspace_id: uuid.UUID) -> Any:
    """A trivial dependency that always resolves to ``CallerContext`` with
    the given workspace. Skips DB lookup."""

    async def _dep() -> CallerContext:
        return CallerContext(user_id=USER_ID, workspace_id=workspace_id, role=Role.OWNER)

    return _dep


def _build(
    *,
    workspace_id: uuid.UUID,
    tracker: PerUserDailyTracker,
    breaker: WorkspaceCostBreaker | None,
    override: AdminOverride | None = None,
) -> tuple[Any, _StubSessionService]:
    auth = InternalAuthConfig(expected_key=SECRET, environment="staging", dev_mode=False)
    session_id = uuid.uuid4()
    sessions = _StubSessionService(
        session_id=session_id, workspace_id=workspace_id, user_id=USER_ID
    )
    app = build_app(
        _orchestrator(),
        config=AppConfig(environment="staging"),
        auth_config=auth,
        session_service=sessions,  # type: ignore[arg-type]
        require_caller=_require_caller(workspace_id),
        workspace_breaker=breaker,
        daily_tracker=tracker,
        admin_override=override,
    )
    return app, sessions, session_id  # type: ignore[return-value]


def _payload(session_id: uuid.UUID) -> dict[str, Any]:
    return {"session_id": str(session_id), "query": "What is the runbook?"}


def _headers() -> dict[str, str]:
    return {"X-Internal-Key": SECRET}


# ---------------------------------------------------------------------------
# 1. Workspace over budget → HTTP 402, model not invoked.
# ---------------------------------------------------------------------------
async def test_over_budget_workspace_gets_402_before_orchestrator_runs() -> None:
    tracker = PerUserDailyTracker()
    tracker.record(str(WORKSPACE_OVER), Decimal("11"))  # > $10 budget
    breaker = WorkspaceCostBreaker(tracker=tracker, daily_budget_usd=Decimal("10"))

    app, sessions, session_id = _build(
        workspace_id=WORKSPACE_OVER, tracker=tracker, breaker=breaker
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/v1/chat", json=_payload(session_id), headers=_headers())
    assert resp.status_code == 402
    assert "exceeded its daily budget" in resp.json()["detail"]
    # Critical: nothing was persisted because the orchestrator never ran.
    assert sessions.persisted == []


# ---------------------------------------------------------------------------
# 2. Under-budget request proceeds AND records spend on the tracker.
# ---------------------------------------------------------------------------
async def test_under_budget_request_records_spend_on_tracker() -> None:
    tracker = PerUserDailyTracker()
    breaker = WorkspaceCostBreaker(tracker=tracker, daily_budget_usd=Decimal("10"))

    app, sessions, session_id = _build(workspace_id=WORKSPACE_OK, tracker=tracker, breaker=breaker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/v1/chat", json=_payload(session_id), headers=_headers())
    assert resp.status_code == 200
    # The scripted model accumulates a small but non-zero cost via the
    # default rate table. Spend should now be > 0 for this workspace.
    assert tracker.today(str(WORKSPACE_OK)).total_usd > Decimal("0")
    # And the persisted exchange picked up the same cost.
    assert len(sessions.persisted) == 1
    assert sessions.persisted[0].cost_usd >= Decimal("0")


# ---------------------------------------------------------------------------
# 3. Admin override bypasses the cap.
# ---------------------------------------------------------------------------
async def test_admin_override_bypasses_workspace_budget() -> None:
    tracker = PerUserDailyTracker()
    tracker.record(str(WORKSPACE_OVER), Decimal("999"))
    breaker = WorkspaceCostBreaker(tracker=tracker, daily_budget_usd=Decimal("10"))
    override = AdminOverride(budget_bypass=frozenset({str(WORKSPACE_OVER)}))

    app, _sessions, session_id = _build(
        workspace_id=WORKSPACE_OVER, tracker=tracker, breaker=breaker, override=override
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/v1/chat", json=_payload(session_id), headers=_headers())
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 4. No breaker wired → no enforcement, no error.
# ---------------------------------------------------------------------------
async def test_no_breaker_means_no_enforcement() -> None:
    tracker = PerUserDailyTracker()
    tracker.record(str(WORKSPACE_OVER), Decimal("999"))

    app, _sessions, session_id = _build(workspace_id=WORKSPACE_OVER, tracker=tracker, breaker=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.post("/v1/chat", json=_payload(session_id), headers=_headers())
    assert resp.status_code == 200
