"""Postgres-backed flag store — reads/writes the feature_flags table
added in migration 0003."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from meridian_feature_flags.rollout import FeatureFlag

SessionFactory = Callable[[], Session]


@dataclass
class PostgresFeatureFlagStore:
    session_factory: SessionFactory

    def get(self, name: str) -> FeatureFlag | None:
        with self.session_factory() as session:
            row = session.execute(
                text(
                    "SELECT name, percentage, kill_switch, allowlist, denylist, updated_at, updated_by "
                    "FROM feature_flags WHERE name = :name"
                ),
                {"name": name},
            ).first()
            if row is None:
                return None
            return FeatureFlag(
                name=row[0],
                percentage=row[1],
                kill_switch=row[2],
                allowlist=list(row[3] or []),
                denylist=list(row[4] or []),
                updated_at=row[5],
                updated_by=row[6],
            )

    def put(self, flag: FeatureFlag) -> None:
        with self.session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO feature_flags "
                    "(name, percentage, kill_switch, allowlist, denylist, updated_at, updated_by) "
                    "VALUES (:name, :percentage, :kill_switch, CAST(:allowlist AS jsonb), "
                    "CAST(:denylist AS jsonb), :updated_at, :updated_by) "
                    "ON CONFLICT (name) DO UPDATE SET "
                    "  percentage = EXCLUDED.percentage, "
                    "  kill_switch = EXCLUDED.kill_switch, "
                    "  allowlist = EXCLUDED.allowlist, "
                    "  denylist = EXCLUDED.denylist, "
                    "  updated_at = EXCLUDED.updated_at, "
                    "  updated_by = EXCLUDED.updated_by"
                ),
                {
                    "name": flag.name,
                    "percentage": flag.percentage,
                    "kill_switch": flag.kill_switch,
                    "allowlist": _to_json(flag.allowlist),
                    "denylist": _to_json(flag.denylist),
                    "updated_at": flag.updated_at,
                    "updated_by": flag.updated_by,
                },
            )
            session.commit()

    def list_all(self) -> list[FeatureFlag]:
        with self.session_factory() as session:
            rows = session.execute(
                text(
                    "SELECT name, percentage, kill_switch, allowlist, denylist, updated_at, updated_by "
                    "FROM feature_flags ORDER BY name"
                )
            ).all()
            return [
                FeatureFlag(
                    name=row[0],
                    percentage=row[1],
                    kill_switch=row[2],
                    allowlist=list(row[3] or []),
                    denylist=list(row[4] or []),
                    updated_at=row[5],
                    updated_by=row[6],
                )
                for row in rows
            ]


def _to_json(items: list[str]) -> str:
    import json as _json

    return _json.dumps(items)
