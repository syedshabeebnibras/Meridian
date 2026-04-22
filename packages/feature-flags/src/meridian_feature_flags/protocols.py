"""Store Protocol — in-memory for tests, Postgres for prod."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from meridian_feature_flags.rollout import FeatureFlag


class FeatureFlagStore(Protocol):
    def get(self, name: str) -> FeatureFlag | None: ...

    def put(self, flag: FeatureFlag) -> None: ...

    def list_all(self) -> list[FeatureFlag]: ...
