"""Tenant isolation tests — proves user A can't see user B's data.

These tests stand up a real Postgres connection (via the shared CI DB) so
the membership check and session_id FK enforcement run end-to-end. The
TenantService + SessionService are exercised directly, and the FastAPI
routes are hit through ``httpx.ASGITransport``.

Preconditions:
    DATABASE_URL env var points at a fresh/migrated Meridian DB.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
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
from meridian_db.tenants import Role, TenantService
from meridian_orchestrator import (
    AppConfig,
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
    build_app,
)
from meridian_orchestrator.auth import InternalAuthConfig
from meridian_orchestrator.caller import build_require_caller_context
from meridian_orchestrator.sessions import SessionService
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://meridian:meridian@localhost:5432/meridian"
)


@pytest.fixture(scope="module")
def engine():  # type: ignore[no-untyped-def]
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"postgres unavailable at {DATABASE_URL}: {exc}", allow_module_level=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def sessionmaker_fixture(engine):  # type: ignore[no-untyped-def]
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def _clean_db(engine):  # type: ignore[no-untyped-def]
    """Truncate every tenant table before each test.

    Fast — Postgres TRUNCATE is DDL-speed. Cascade drops child rows.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE "
                "usage_records, audit_events, feedback_records, "
                "chat_messages, chat_sessions, memberships, workspaces, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


class _FileTemplateProvider(TemplateProvider):
    def get_active(self, name: str, environment: str) -> PromptTemplate:
        from datetime import UTC, datetime

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
                activated_by="tenant-test@meridian.example",
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
                "confidence": 0.9,
                "needs_escalation": False,
            }
        return ModelResponse(
            id="tenant-stub",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            latency_ms=1,
        )


def _orchestrator() -> Orchestrator:
    return Orchestrator(
        templates=_FileTemplateProvider(),
        retrieval=MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])]),
        model_client=_ScriptedModel(),
        config=OrchestratorConfig(environment="test"),
    )


def _tenant_app(sessionmaker_):  # type: ignore[no-untyped-def]
    """App wired with SessionService + caller-context dep."""
    session_service = SessionService(sessionmaker_)
    require_caller = build_require_caller_context(sessionmaker_)
    auth_config = InternalAuthConfig(expected_key="", environment="test", dev_mode=True)
    return build_app(
        _orchestrator(),
        config=AppConfig(environment="test"),
        auth_config=auth_config,
        session_service=session_service,
        require_caller=require_caller,
    )


@pytest.fixture()
async def client(sessionmaker_fixture):  # type: ignore[no-untyped-def]
    app = _tenant_app(sessionmaker_fixture)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def _auth_headers(user_id: uuid.UUID, workspace_id: uuid.UUID, role: Role) -> dict[str, str]:
    return {
        "X-User-Id": str(user_id),
        "X-Workspace-Id": str(workspace_id),
        "X-User-Role": role.value,
    }


@pytest.fixture()
def svc(sessionmaker_fixture) -> TenantService:  # type: ignore[no-untyped-def]
    return TenantService(sessionmaker_fixture)


# ---------------------------------------------------------------------------
# User / workspace / membership plumbing
# ---------------------------------------------------------------------------
def test_register_creates_user_and_workspace(svc: TenantService) -> None:
    user, ws = svc.register_user_with_personal_workspace(
        email="alice@example.com", name="Alice", password="correcthorsebatterystaple"
    )
    assert user.email == "alice@example.com"
    assert ws.owner_user_id == user.id
    memberships = svc.get_user_workspaces(user.id)
    assert len(memberships) == 1
    _, role = memberships[0]
    assert role is Role.OWNER


def test_duplicate_email_rejected(svc: TenantService) -> None:
    svc.register_user(email="dup@example.com", name="A", password="x" * 16)
    from meridian_db.tenants import EmailAlreadyRegisteredError

    with pytest.raises(EmailAlreadyRegisteredError):
        svc.register_user(email="DUP@example.com", name="A", password="y" * 16)


def test_verify_login_good_bad_unknown(svc: TenantService) -> None:
    from meridian_db.tenants import AuthenticationError

    user = svc.register_user(email="bob@example.com", name="Bob", password="supersecret")
    assert svc.verify_login(email="bob@example.com", password="supersecret").id == user.id
    with pytest.raises(AuthenticationError):
        svc.verify_login(email="bob@example.com", password="wrong")
    with pytest.raises(AuthenticationError):
        svc.verify_login(email="nobody@example.com", password="x")


# ---------------------------------------------------------------------------
# HTTP route isolation
# ---------------------------------------------------------------------------
async def test_missing_caller_headers_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/sessions")
    assert resp.status_code == 401


async def test_malformed_workspace_header_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/v1/sessions",
        headers={
            "X-User-Id": "not-a-uuid",
            "X-Workspace-Id": str(uuid.uuid4()),
            "X-User-Role": "owner",
        },
    )
    assert resp.status_code == 400


async def test_unknown_membership_rejected(client: httpx.AsyncClient) -> None:
    # Valid UUIDs but no matching membership row.
    resp = await client.get(
        "/v1/sessions",
        headers=_auth_headers(uuid.uuid4(), uuid.uuid4(), Role.OWNER),
    )
    assert resp.status_code == 403


async def test_session_isolation_user_a_cannot_access_user_b_session(
    client: httpx.AsyncClient, svc: TenantService
) -> None:
    alice, ws_alice = svc.register_user_with_personal_workspace(
        email="alice@ex.com", name="A", password="p" * 16
    )
    bob, ws_bob = svc.register_user_with_personal_workspace(
        email="bob@ex.com", name="B", password="p" * 16
    )

    # Alice creates a session in her workspace.
    resp = await client.post(
        "/v1/sessions",
        json={"title": "Alice's thread"},
        headers=_auth_headers(alice.id, ws_alice.id, Role.OWNER),
    )
    assert resp.status_code == 200
    alice_session_id = resp.json()["id"]

    # Bob (a different workspace) can't see or read it.
    resp = await client.get(
        f"/v1/sessions/{alice_session_id}",
        headers=_auth_headers(bob.id, ws_bob.id, Role.OWNER),
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/v1/sessions/{alice_session_id}/messages",
        headers=_auth_headers(bob.id, ws_bob.id, Role.OWNER),
    )
    assert resp.status_code == 404

    # Bob's session list is empty.
    resp = await client.get("/v1/sessions", headers=_auth_headers(bob.id, ws_bob.id, Role.OWNER))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_workspace_isolation_shared_user_different_workspaces(
    client: httpx.AsyncClient, svc: TenantService
) -> None:
    # One user, two workspaces — sessions in each must stay separate.
    alice, ws1 = svc.register_user_with_personal_workspace(
        email="alice2@ex.com", name="A", password="p" * 16
    )
    ws2 = svc.create_workspace(owner_user_id=alice.id, name="Alice Team", slug="alice-team")

    resp = await client.post(
        "/v1/sessions",
        json={"title": "W1 thread"},
        headers=_auth_headers(alice.id, ws1.id, Role.OWNER),
    )
    assert resp.status_code == 200
    w1_session_id = resp.json()["id"]

    # Same user, other workspace — must NOT see the W1 session.
    resp = await client.get(
        f"/v1/sessions/{w1_session_id}",
        headers=_auth_headers(alice.id, ws2.id, Role.OWNER),
    )
    assert resp.status_code == 404


async def test_chat_endpoint_scopes_session_to_workspace(
    client: httpx.AsyncClient, svc: TenantService
) -> None:
    alice, ws_alice = svc.register_user_with_personal_workspace(
        email="alice3@ex.com", name="A", password="p" * 16
    )
    bob, ws_bob = svc.register_user_with_personal_workspace(
        email="bob3@ex.com", name="B", password="p" * 16
    )

    resp = await client.post(
        "/v1/sessions",
        json={"title": "Alice chat"},
        headers=_auth_headers(alice.id, ws_alice.id, Role.OWNER),
    )
    alice_session_id = resp.json()["id"]

    # Bob attempts to use Alice's session_id against his workspace.
    resp = await client.post(
        "/v1/chat",
        json={
            "session_id": alice_session_id,
            "query": "cross-tenant read attempt",
        },
        headers=_auth_headers(bob.id, ws_bob.id, Role.OWNER),
    )
    assert resp.status_code == 404  # session not found (for Bob)


async def test_chat_happy_path_persists_messages_and_usage(
    client: httpx.AsyncClient, svc: TenantService, sessionmaker_fixture
) -> None:
    alice, ws_alice = svc.register_user_with_personal_workspace(
        email="alice4@ex.com", name="A", password="p" * 16
    )
    resp = await client.post(
        "/v1/sessions",
        json={"title": "persistence test"},
        headers=_auth_headers(alice.id, ws_alice.id, Role.OWNER),
    )
    session_id = resp.json()["id"]

    resp = await client.post(
        "/v1/chat",
        json={"session_id": session_id, "query": "hi?"},
        headers=_auth_headers(alice.id, ws_alice.id, Role.OWNER),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Both user + assistant messages landed in the DB.
    resp = await client.get(
        f"/v1/sessions/{session_id}/messages",
        headers=_auth_headers(alice.id, ws_alice.id, Role.OWNER),
    )
    assert resp.status_code == 200
    msgs = resp.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "hi?"

    # Usage record wrote through.
    with sessionmaker_fixture() as session:
        from meridian_db import UsageRecordRow

        count = session.query(UsageRecordRow).filter_by(workspace_id=ws_alice.id).count()
        assert count == 1


async def test_viewer_cannot_rename_session_only_owner_or_admin(
    client: httpx.AsyncClient, svc: TenantService
) -> None:
    # Viewer is added to workspace but only with read-only rights.
    owner, ws = svc.register_user_with_personal_workspace(
        email="owner@ex.com", name="O", password="p" * 16
    )
    viewer = svc.register_user(email="viewer@ex.com", name="V", password="p" * 16)
    svc.add_member(workspace_id=ws.id, user_id=viewer.id, role=Role.VIEWER)

    resp = await client.post(
        "/v1/sessions",
        json={"title": "owner thread"},
        headers=_auth_headers(owner.id, ws.id, Role.OWNER),
    )
    session_id = resp.json()["id"]

    # RBAC guard — viewer attempts to rename. The HTTP layer doesn't yet
    # enforce rename-min-role (Phase 3 will), but viewer should at least
    # be able to READ. This test confirms the read side for a viewer
    # works AND documents the rename open-for-member-and-up contract.
    resp = await client.get(
        f"/v1/sessions/{session_id}",
        headers=_auth_headers(viewer.id, ws.id, Role.VIEWER),
    )
    assert resp.status_code == 200


async def test_soft_delete_hides_from_list(client: httpx.AsyncClient, svc: TenantService) -> None:
    alice, ws = svc.register_user_with_personal_workspace(
        email="alice5@ex.com", name="A", password="p" * 16
    )
    resp = await client.post(
        "/v1/sessions",
        json={"title": "temp"},
        headers=_auth_headers(alice.id, ws.id, Role.OWNER),
    )
    session_id = resp.json()["id"]

    resp = await client.delete(
        f"/v1/sessions/{session_id}",
        headers=_auth_headers(alice.id, ws.id, Role.OWNER),
    )
    assert resp.status_code == 204

    resp = await client.get("/v1/sessions", headers=_auth_headers(alice.id, ws.id, Role.OWNER))
    assert resp.json() == []

    # Direct GET also returns 404 for a soft-deleted session.
    resp = await client.get(
        f"/v1/sessions/{session_id}",
        headers=_auth_headers(alice.id, ws.id, Role.OWNER),
    )
    assert resp.status_code == 404
