"""In-memory flag store — tests + single-process dev."""

from __future__ import annotations

from dataclasses import dataclass, field

from meridian_feature_flags.rollout import FeatureFlag


@dataclass
class InMemoryFeatureFlagStore:
    _flags: dict[str, FeatureFlag] = field(default_factory=dict)

    def get(self, name: str) -> FeatureFlag | None:
        return self._flags.get(name)

    def put(self, flag: FeatureFlag) -> None:
        self._flags[flag.name] = flag

    def list_all(self) -> list[FeatureFlag]:
        return sorted(self._flags.values(), key=lambda f: f.name)
