"""PromptRegistry — versioned, immutable templates with flip-style rollback.

Design (Section 19 D3 + Section 6 §Prompt registry design):

- `prompt_templates` rows are **immutable**. A new prompt behaviour = a new
  row with version = max(version) + 1. The registry never UPDATEs a template.
- `prompt_activations` carries which (name, environment) pair is live. On
  activate, the previous active row is archived (status='archived',
  deactivated_at=now()) and a fresh row is inserted for the new version.
- Rollback looks up the most recently archived activation for (name, env)
  and re-activates that template. This is a pure row operation — no code
  deploy, no DDL.
- Every mutation writes a `prompt_audit_log` row so change management has a
  full trail.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    EvalResults,
    ModelTier,
    PromptTemplate,
    TokenBudget,
)
from meridian_db import PromptActivation, PromptAuditLog, PromptTemplateRow
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from collections.abc import Iterator


SessionFactory = Callable[[], Session]


class PromptVersionNotFoundError(LookupError):
    """No template row matches the requested (name, version)."""


class ActiveTemplateNotFoundError(LookupError):
    """No active activation exists for (name, environment)."""


class NoPriorActivationError(RuntimeError):
    """Attempted to roll back but there is no archived activation to revert to."""


class PromptRegistry:
    """CRUD + activation + rollback over the Phase 1 registry schema."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _row_to_template(
        row: PromptTemplateRow, activation: PromptActivation | None
    ) -> PromptTemplate:
        """Assemble a PromptTemplate contract from the split ORM tables."""

        activation_info: ActivationInfo
        if activation is not None:
            activation_info = ActivationInfo(
                environment=activation.environment,
                status=ActivationStatus(activation.status),
                canary_percentage=activation.canary_percentage,
                activated_at=activation.activated_at,
                activated_by=activation.activated_by,
            )
        else:
            # A template exists without any activation — e.g. drafts that were
            # uploaded but never promoted. Expose a DRAFT ActivationInfo so the
            # Pydantic contract stays total.
            activation_info = ActivationInfo(
                environment="none",
                status=ActivationStatus.DRAFT,
                canary_percentage=0,
                activated_at=row.created_at,
                activated_by=row.created_by,
            )

        eval_results: EvalResults | None = None
        if row.eval_results is not None:
            eval_results = EvalResults.model_validate(row.eval_results)

        return PromptTemplate(
            name=row.name,
            version=row.version,
            model_tier=ModelTier(row.model_tier),
            min_model=row.min_model,
            template=row.template,
            parameters=list(row.parameters),
            schema_ref=row.schema_ref,
            few_shot_dataset=row.few_shot_dataset,
            token_budget=TokenBudget.model_validate(row.token_budget),
            cache_control=CacheControl.model_validate(row.cache_control),
            activation=activation_info,
            eval_results=eval_results,
        )

    @staticmethod
    def _active_for(
        session: Session, name: str, environment: str
    ) -> tuple[PromptTemplateRow, PromptActivation] | None:
        stmt = (
            select(PromptTemplateRow, PromptActivation)
            .join(PromptActivation, PromptActivation.template_id == PromptTemplateRow.id)
            .where(PromptTemplateRow.name == name)
            .where(PromptActivation.environment == environment)
            .where(PromptActivation.status.in_([ActivationStatus.ACTIVE, ActivationStatus.CANARY]))
            .order_by(PromptActivation.activated_at.desc())
            .limit(1)
        )
        return session.execute(stmt).first()  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def create_version(self, template: PromptTemplate, *, created_by: str) -> int:
        """Append a new immutable version. Returns the assigned version number.

        The caller's `template.version` is advisory — the registry auto-assigns
        max(version) + 1 so concurrent callers never clash. The returned value
        is authoritative.
        """
        with self._session() as session:
            next_version = session.execute(
                select(func.coalesce(func.max(PromptTemplateRow.version), 0) + 1).where(
                    PromptTemplateRow.name == template.name
                )
            ).scalar_one()

            row = PromptTemplateRow(
                name=template.name,
                version=next_version,
                model_tier=template.model_tier.value,
                min_model=template.min_model,
                template=template.template,
                parameters=list(template.parameters),
                schema_ref=template.schema_ref,
                few_shot_dataset=template.few_shot_dataset,
                token_budget=template.token_budget.model_dump(),
                cache_control=template.cache_control.model_dump(),
                eval_results=(
                    template.eval_results.model_dump() if template.eval_results else None
                ),
                created_by=created_by,
            )
            session.add(row)
            session.add(
                PromptAuditLog(
                    prompt_name=template.name,
                    action="create",
                    from_version=None,
                    to_version=next_version,
                    environment=None,
                    actor=created_by,
                    reason=None,
                )
            )
            return int(next_version)

    def get_version(self, name: str, version: int) -> PromptTemplate:
        with self._session() as session:
            row = session.execute(
                select(PromptTemplateRow)
                .where(PromptTemplateRow.name == name)
                .where(PromptTemplateRow.version == version)
            ).scalar_one_or_none()
            if row is None:
                raise PromptVersionNotFoundError(f"no template {name} v{version}")
            return self._row_to_template(row, activation=None)

    def get_active(self, name: str, environment: str) -> PromptTemplate:
        with self._session() as session:
            result = self._active_for(session, name, environment)
            if result is None:
                raise ActiveTemplateNotFoundError(
                    f"no active template {name!r} in env {environment!r}"
                )
            row, activation = result
            return self._row_to_template(row, activation)

    def list_versions(self, name: str) -> list[PromptTemplate]:
        with self._session() as session:
            rows = (
                session.execute(
                    select(PromptTemplateRow)
                    .where(PromptTemplateRow.name == name)
                    .order_by(PromptTemplateRow.version)
                )
                .scalars()
                .all()
            )
            return [self._row_to_template(r, activation=None) for r in rows]

    def activate(
        self,
        name: str,
        version: int,
        *,
        environment: str,
        actor: str,
        canary_percentage: int = 0,
        reason: str | None = None,
    ) -> None:
        """Flip the live version for (name, environment) to `version`.

        If a different version is currently active in this environment, it is
        archived (`status = "archived"`, `deactivated_at = now()`) in the same
        transaction as the new insert so there is never a moment when no
        version is active for this pair.
        """
        if not 0 <= canary_percentage <= 100:
            raise ValueError(f"canary_percentage must be in [0, 100], got {canary_percentage}")

        with self._session() as session:
            target = session.execute(
                select(PromptTemplateRow)
                .where(PromptTemplateRow.name == name)
                .where(PromptTemplateRow.version == version)
            ).scalar_one_or_none()
            if target is None:
                raise PromptVersionNotFoundError(f"no template {name} v{version}")

            current = self._active_for(session, name, environment)
            from_version = current[0].version if current else None

            # Archive the currently-active row(s).
            session.execute(
                update(PromptActivation)
                .where(PromptActivation.environment == environment)
                .where(
                    PromptActivation.template_id.in_(
                        select(PromptTemplateRow.id).where(PromptTemplateRow.name == name)
                    )
                )
                .where(
                    PromptActivation.status.in_([ActivationStatus.ACTIVE, ActivationStatus.CANARY])
                )
                .values(
                    status=ActivationStatus.ARCHIVED.value,
                    deactivated_at=datetime.now(tz=UTC),
                )
            )

            status = ActivationStatus.CANARY if canary_percentage > 0 else ActivationStatus.ACTIVE
            session.add(
                PromptActivation(
                    template_id=target.id,
                    environment=environment,
                    status=status.value,
                    canary_percentage=canary_percentage,
                    activated_by=actor,
                )
            )
            session.add(
                PromptAuditLog(
                    prompt_name=name,
                    action="activate",
                    from_version=from_version,
                    to_version=version,
                    environment=environment,
                    actor=actor,
                    reason=reason,
                )
            )

    def rollback(
        self,
        name: str,
        *,
        environment: str,
        actor: str,
        reason: str | None = None,
    ) -> int:
        """Revert to the most recently archived version in this environment.

        Returns the version number that is now active after rollback. Raises
        NoPriorActivationError if there is no archived row to revert to
        (e.g. the prompt has only ever had one active version).
        """
        with self._session() as session:
            current = self._active_for(session, name, environment)
            current_version = current[0].version if current else None

            # Find the most recently archived activation for this (name, env).
            stmt = (
                select(PromptTemplateRow, PromptActivation)
                .join(
                    PromptActivation,
                    PromptActivation.template_id == PromptTemplateRow.id,
                )
                .where(PromptTemplateRow.name == name)
                .where(PromptActivation.environment == environment)
                .where(PromptActivation.status == ActivationStatus.ARCHIVED.value)
                .order_by(PromptActivation.deactivated_at.desc().nulls_last())
                .limit(1)
            )
            previous = session.execute(stmt).first()
            if previous is None:
                raise NoPriorActivationError(
                    f"no archived activation to revert to for {name!r} in env {environment!r}"
                )
            prev_row, _prev_activation = previous

        # Re-activate via the standard path (gives us audit + archive semantics).
        self.activate(
            name,
            version=prev_row.version,
            environment=environment,
            actor=actor,
            reason=reason or f"rollback from v{current_version}",
        )

        # The last audit row wrote action='activate'; rewrite it as 'rollback'
        # so dashboards filtering by action see the intent.
        with self._session() as session:
            latest_audit = session.execute(
                select(PromptAuditLog)
                .where(PromptAuditLog.prompt_name == name)
                .where(PromptAuditLog.environment == environment)
                .order_by(PromptAuditLog.created_at.desc())
                .limit(1)
            ).scalar_one()
            latest_audit.action = "rollback"

        return int(prev_row.version)
