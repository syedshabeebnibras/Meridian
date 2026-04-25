"""Tenant service — user registration, workspace creation, memberships.

This module centralises every write path that touches ``users``,
``workspaces``, and ``memberships``. Callers outside ``meridian_db``
should go through ``TenantService`` rather than hand-rolling SQL so
business invariants (one owner, slug generation, argon2 hashing) stay
in a single place.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from meridian_db.models import MembershipRow, UserRow, WorkspaceRow


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        """Higher == more privileged. Used for ``role >= other`` checks."""
        return _ROLE_RANK[self]


_ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.ADMIN: 2,
    Role.OWNER: 3,
}


class TenantError(RuntimeError):
    """Base class for tenant-service failures."""


class EmailAlreadyRegisteredError(TenantError):
    pass


class AuthenticationError(TenantError):
    """Raised when login credentials don't verify. Intentionally opaque so
    callers can't distinguish "unknown email" from "wrong password" — mitigates
    account enumeration."""


class WorkspaceNotFoundError(TenantError):
    pass


class MembershipNotFoundError(TenantError):
    pass


@dataclass(frozen=True)
class UserSummary:
    id: uuid.UUID
    email: str
    name: str


@dataclass(frozen=True)
class WorkspaceSummary:
    id: uuid.UUID
    name: str
    slug: str
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class MembershipSummary:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role


# Module-level hasher is fine — ``argon2-cffi`` uses default parameters
# tuned for server hardware (t=3, m=65536, p=4). Operators can swap in
# custom parameters via env var if needed.
_HASHER = PasswordHasher()


# Strip to chars that read cleanly in URLs.
_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


def _slugify(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "-")
    cleaned = _SLUG_SAFE.sub("", lowered).strip("-")
    return cleaned[:48] or "workspace"


class TenantService:
    """Write-path for users, workspaces, and memberships.

    Takes a SQLAlchemy ``sessionmaker`` rather than a single session so each
    call runs in its own transaction — avoids implicit cross-request state.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Users + auth
    # ------------------------------------------------------------------
    def register_user(self, *, email: str, name: str, password: str) -> UserSummary:
        """Create a user with an argon2id password hash.

        Raises ``EmailAlreadyRegisteredError`` on duplicate email (case-insensitive).
        """
        password_hash = _HASHER.hash(password)
        email_lc = email.strip().lower()
        with self._session_factory.begin() as session:
            existing = session.scalar(select(UserRow).where(UserRow.email == email_lc))
            if existing is not None:
                raise EmailAlreadyRegisteredError(email_lc)
            user = UserRow(
                id=uuid.uuid4(),
                email=email_lc,
                name=name.strip(),
                password_hash=password_hash,
            )
            session.add(user)
            try:
                session.flush()
            except IntegrityError as exc:
                # Race: another thread registered the same email between
                # our SELECT and INSERT. Treat as duplicate.
                raise EmailAlreadyRegisteredError(email_lc) from exc
            return UserSummary(id=user.id, email=user.email, name=user.name)

    def verify_login(self, *, email: str, password: str) -> UserSummary:
        """Return the UserSummary iff credentials match.

        Always runs argon2 verify even on missing users so response times
        are comparable and an attacker can't distinguish cases.
        """
        email_lc = email.strip().lower()
        with self._session_factory() as session:
            user = session.scalar(select(UserRow).where(UserRow.email == email_lc))
            # Dummy hash of a known-bad password so timing stays symmetric when
            # the email doesn't exist. Without this, a short-circuit leaks info.
            candidate_hash = (
                user.password_hash
                if user is not None and user.password_hash is not None
                else _DUMMY_HASH
            )
            try:
                _HASHER.verify(candidate_hash, password)
            except VerifyMismatchError as exc:
                raise AuthenticationError("invalid credentials") from exc
            if user is None:
                raise AuthenticationError("invalid credentials")
            return UserSummary(id=user.id, email=user.email, name=user.name)

    def get_user_by_email(self, email: str) -> UserSummary | None:
        with self._session_factory() as session:
            user = session.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))
            if user is None:
                return None
            return UserSummary(id=user.id, email=user.email, name=user.name)

    def get_user(self, user_id: uuid.UUID) -> UserSummary | None:
        with self._session_factory() as session:
            user = session.get(UserRow, user_id)
            if user is None:
                return None
            return UserSummary(id=user.id, email=user.email, name=user.name)

    # ------------------------------------------------------------------
    # Workspaces + memberships
    # ------------------------------------------------------------------
    def create_workspace(
        self, *, owner_user_id: uuid.UUID, name: str, slug: str | None = None
    ) -> WorkspaceSummary:
        """Create a workspace and make the owner a member with role=owner."""
        final_slug = _slugify(slug or name) or "workspace"
        with self._session_factory.begin() as session:
            workspace = WorkspaceRow(
                id=uuid.uuid4(),
                name=name.strip(),
                slug=final_slug,
                owner_user_id=owner_user_id,
            )
            session.add(workspace)
            session.flush()
            membership = MembershipRow(
                user_id=owner_user_id,
                workspace_id=workspace.id,
                role=Role.OWNER.value,
            )
            session.add(membership)
            session.flush()
            return WorkspaceSummary(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                owner_user_id=workspace.owner_user_id,
            )

    def register_user_with_personal_workspace(
        self, *, email: str, name: str, password: str
    ) -> tuple[UserSummary, WorkspaceSummary]:
        """Convenience: sign-up creates user + personal workspace atomically."""
        user = self.register_user(email=email, name=name, password=password)
        workspace = self.create_workspace(
            owner_user_id=user.id,
            name=f"{user.name}'s workspace" if user.name else "Personal workspace",
            slug=_slugify(user.email.split("@")[0]) + "-" + uuid.uuid4().hex[:4],
        )
        return user, workspace

    def get_user_workspaces(self, user_id: uuid.UUID) -> list[tuple[WorkspaceSummary, Role]]:
        """Return every (workspace, role) the user belongs to."""
        with self._session_factory() as session:
            rows = session.execute(
                select(WorkspaceRow, MembershipRow)
                .join(MembershipRow, MembershipRow.workspace_id == WorkspaceRow.id)
                .where(MembershipRow.user_id == user_id)
                .where(WorkspaceRow.deleted_at.is_(None))
                .order_by(WorkspaceRow.created_at)
            ).all()
            return [
                (
                    WorkspaceSummary(
                        id=w.id, name=w.name, slug=w.slug, owner_user_id=w.owner_user_id
                    ),
                    Role(m.role),
                )
                for w, m in rows
            ]

    def get_membership(
        self, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> MembershipSummary | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(MembershipRow)
                .where(MembershipRow.user_id == user_id)
                .where(MembershipRow.workspace_id == workspace_id)
            )
            if row is None:
                return None
            return MembershipSummary(
                user_id=row.user_id, workspace_id=row.workspace_id, role=Role(row.role)
            )

    def add_member(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: Role
    ) -> MembershipSummary:
        with self._session_factory.begin() as session:
            ws = session.get(WorkspaceRow, workspace_id)
            if ws is None:
                raise WorkspaceNotFoundError(str(workspace_id))
            row = MembershipRow(user_id=user_id, workspace_id=workspace_id, role=role.value)
            session.add(row)
            session.flush()
            return MembershipSummary(user_id=user_id, workspace_id=workspace_id, role=role)

    def remove_member(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with self._session_factory.begin() as session:
            row = session.scalar(
                select(MembershipRow)
                .where(MembershipRow.workspace_id == workspace_id)
                .where(MembershipRow.user_id == user_id)
            )
            if row is None:
                raise MembershipNotFoundError(f"{user_id} in {workspace_id}")
            # Owners can't remove themselves; refuse to orphan the workspace.
            if row.role == Role.OWNER.value:
                raise TenantError("workspace owner cannot be removed")
            session.delete(row)


# A precomputed argon2 hash of an unguessable string. Used when we need to
# keep the timing profile symmetric (see verify_login). Generated once at
# import time so tests don't need to mock it.
_DUMMY_HASH = _HASHER.hash(f"__dummy__{uuid.uuid4()}")


def require_role(actual: Role, *, at_least: Role) -> None:
    """Raise ``PermissionError`` when the actual role is below the floor."""
    if actual.rank < at_least.rank:
        raise PermissionError(f"requires role >= {at_least.value}, got {actual.value}")
