"""Caller-context dependency: trust the edge, verify the membership.

The Next.js server proxy forwards three identity headers after it has
verified the user's JWT:

    X-User-Id        — authenticated user (uuid)
    X-Workspace-Id   — selected workspace (uuid)
    X-User-Role      — owner | admin | member | viewer

These headers are trusted ONLY after ``X-Internal-Key`` has been verified
(see ``auth.py``). As defence-in-depth we re-check the ``Membership`` row
against the DB on every request — if the edge is compromised or the role
changed mid-session, the orchestrator still refuses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from collections.abc import Awaitable, Callable

from fastapi import Header, HTTPException, status
from meridian_db.tenants import Role, TenantService
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class CallerContext:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role

    def require(self, *, at_least: Role) -> None:
        if self.role.rank < at_least.rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role >= {at_least.value}, got {self.role.value}",
            )


def build_require_caller_context(
    session_factory: sessionmaker[Session] | None,
) -> Callable[[str | None, str | None, str | None], Awaitable[CallerContext]]:
    """Build a FastAPI dependency that resolves the caller context.

    Takes the sessionmaker at build time so each app instance binds to
    the right DB. If ``session_factory`` is None we still parse the
    headers but skip the membership re-check — used only in unit tests
    that don't have a DB.
    """

    tenant_service = TenantService(session_factory) if session_factory is not None else None

    async def require_caller_context(
        x_user_id: str | None = Header(default=None, alias="X-User-Id"),
        x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
        x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    ) -> CallerContext:
        if not x_user_id or not x_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing caller identity headers",
            )
        try:
            user_id = uuid.UUID(x_user_id)
            workspace_id = uuid.UUID(x_workspace_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="malformed identity header",
            ) from exc

        # Re-check membership from the DB.
        if tenant_service is not None:
            membership = tenant_service.get_membership(user_id=user_id, workspace_id=workspace_id)
            if membership is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="no membership in this workspace",
                )
            verified_role = membership.role
        else:
            # No DB (unit tests) — trust the edge-supplied role.
            try:
                verified_role = Role(x_user_role or "member")
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="malformed role header",
                ) from exc

        return CallerContext(user_id=user_id, workspace_id=workspace_id, role=verified_role)

    return require_caller_context
