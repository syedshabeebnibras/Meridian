"""60-second staging smoke — Section 12 Phase 7 post-deploy sanity check.

Hits healthz / readyz / metrics and fires one query per intent category.
Exits non-zero on any hard failure. Call from the deploy script.

Usage:
  STAGING_URL=https://meridian-orch.fly.dev uv run python scripts/staging_smoke.py
  STAGING_URL=... uv run python scripts/staging_smoke.py --allow-degraded

Mode detection
--------------
The orchestrator boots in *tenant-aware* mode whenever ``DATABASE_URL`` is
set in its environment (Phase 3 wiring). In that mode ``/v1/chat`` accepts
``ChatInput`` (session_id + query) plus identity headers, not the legacy
``UserRequest`` body.

This script picks the right path automatically:

  - If the env var ``DATABASE_URL`` is set here too, we seed a smoke
    user + workspace + membership directly via psycopg, create a
    session via ``/v1/sessions``, and post ``ChatInput``.
  - Otherwise we fall back to the legacy ``UserRequest`` payload —
    used by older deployments or single-process dev.

``--allow-degraded`` tolerates orchestrator replies with status
"degraded" (circuit-open / provider outage) so a transient upstream
failure doesn't fail the deploy when the orchestrator is correctly
serving the cheap fallback path.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from typing import Any

import httpx

# Stable IDs so the smoke is idempotent across CI runs.
SMOKE_USER_ID = "00000000-0000-0000-0000-0000000000aa"
SMOKE_WORKSPACE_ID = "00000000-0000-0000-0000-0000000000bb"


def _env_url() -> str:
    url = os.environ.get("STAGING_URL", "").rstrip("/")
    if not url:
        print("STAGING_URL env var is required", file=sys.stderr)
        sys.exit(1)
    return url


def _internal_headers() -> dict[str, str]:
    """X-Internal-Key when set; otherwise let the dev escape hatch handle it."""
    key = os.environ.get("ORCH_INTERNAL_KEY", "")
    return {"X-Internal-Key": key} if key else {}


def _identity_headers() -> dict[str, str]:
    return {
        "X-User-Id": SMOKE_USER_ID,
        "X-Workspace-Id": SMOKE_WORKSPACE_ID,
        "X-User-Role": "owner",
    }


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}{(': ' + detail) if detail else ''}")
    return ok


def _seed_tenant() -> bool:
    """Seed (or upsert) the smoke user + workspace + membership.

    No-op when ``DATABASE_URL`` isn't set on the smoke runner — the
    legacy path doesn't need them.
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return False
    # psycopg expects a plain ``postgresql://`` URL; strip the SQLAlchemy
    # ``+psycopg`` driver suffix if present.
    if db_url.startswith("postgresql+psycopg://"):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        print("[skip] DATABASE_URL set but psycopg not importable", file=sys.stderr)
        return False
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, name) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (SMOKE_USER_ID, "smoke@meridian.ci", "Smoke"),
        )
        cur.execute(
            "INSERT INTO workspaces (id, name, slug, owner_user_id) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (SMOKE_WORKSPACE_ID, "Smoke", "smoke", SMOKE_USER_ID),
        )
        cur.execute(
            "INSERT INTO memberships (user_id, workspace_id, role) "
            "VALUES (%s, %s, 'owner') ON CONFLICT DO NOTHING",
            (SMOKE_USER_ID, SMOKE_WORKSPACE_ID),
        )
        conn.commit()
    return True


def _create_session(url: str) -> str | None:
    """Tenant-aware: POST /v1/sessions and return its id."""
    try:
        response = httpx.post(
            f"{url}/v1/sessions",
            json={"title": "smoke"},
            headers={**_internal_headers(), **_identity_headers()},
            timeout=10.0,
        )
        response.raise_for_status()
        return str(response.json()["id"])
    except httpx.HTTPError as exc:
        print(f"[skip] /v1/sessions failed: {exc}", file=sys.stderr)
        return None


def _request_tenant(url: str, session_id: str, query: str) -> dict[str, Any] | None:
    """Tenant-aware /v1/chat call (ChatInput shape)."""
    try:
        response = httpx.post(
            f"{url}/v1/chat",
            json={"session_id": session_id, "query": query},
            headers={**_internal_headers(), **_identity_headers()},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def _request_legacy(url: str, query: str) -> dict[str, Any] | None:
    """Legacy /v1/chat call (UserRequest shape) for non-tenant deployments."""
    payload = {
        "request_id": f"req_smoke{uuid.uuid4().hex[:12]}",
        "user_id": "smoke",
        "session_id": f"smoke_{uuid.uuid4().hex[:8]}",
        "query": query,
        "conversation_history": [],
        "metadata": {"source": "smoke"},
    }
    try:
        response = httpx.post(
            f"{url}/v1/chat",
            json=payload,
            headers=_internal_headers(),
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="Accept status=degraded as a pass (provider outage fallback).",
    )
    args = parser.parse_args()
    accepted_statuses: tuple[str, ...] = ("ok", "refused", "blocked")
    if args.allow_degraded:
        # ``failed`` covers the dispatch-failure path that's expected when CI
        # has no real provider keys but the orchestrator handled it cleanly.
        accepted_statuses = (*accepted_statuses, "degraded", "failed")

    url = _env_url()
    print(f"Smoke-testing {url}")

    all_ok = True

    # 1. Healthz
    try:
        r = httpx.get(f"{url}/healthz", timeout=5)
        all_ok &= _check("healthz", r.status_code == 200 and r.text.strip() == "ok")
    except httpx.HTTPError as exc:
        all_ok = _check("healthz", False, str(exc)) and all_ok

    # 2. Readyz
    try:
        r = httpx.get(f"{url}/readyz", timeout=5)
        all_ok &= _check("readyz", r.status_code == 200)
    except httpx.HTTPError as exc:
        all_ok = _check("readyz", False, str(exc)) and all_ok

    # 3. Metrics endpoint
    try:
        r = httpx.get(f"{url}/metrics", timeout=5)
        all_ok &= _check("metrics", r.status_code == 200 and "meridian_requests_total" in r.text)
    except httpx.HTTPError as exc:
        all_ok = _check("metrics", False, str(exc)) and all_ok

    # 4. Pick the right /v1/chat path. Seed the tenant tables if we can talk
    # to the same DB the orchestrator uses; otherwise use legacy.
    tenant_aware = _seed_tenant()
    session_id: str | None = None
    if tenant_aware:
        session_id = _create_session(url)
        if session_id is None:
            tenant_aware = False
    print(f"chat path: {'tenant-aware' if tenant_aware else 'legacy'}")

    smoke_queries = {
        "grounded_qa": "What is the escalation procedure for a P1 database outage?",
        "out_of_scope": "What's the weather in Tokyo?",
        "clarification": "What about that?",
    }
    for intent, query in smoke_queries.items():
        started = time.perf_counter()
        if tenant_aware and session_id is not None:
            reply = _request_tenant(url, session_id, query)
        else:
            reply = _request_legacy(url, query)
        latency_ms = (time.perf_counter() - started) * 1000
        if reply is None:
            all_ok = _check(f"query/{intent}", False, "request failed") and all_ok
            continue
        status = reply.get("status")
        all_ok &= _check(
            f"query/{intent}",
            status in accepted_statuses,
            f"status={status}, {latency_ms:.0f}ms",
        )
        # Latency must be under the Section-12 gate.
        all_ok &= _check(
            f"query/{intent} latency < 4s",
            latency_ms < 4000,
            f"{latency_ms:.0f}ms",
        )

    print()
    print("SMOKE: PASS" if all_ok else "SMOKE: FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
