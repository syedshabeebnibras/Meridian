"""Feature flag system for the Phase 8 gradual rollout.

Three decision inputs, checked in order:
  1. Kill switch — when true, every user is denied (emergency brake).
  2. Per-user allowlist — explicit yes/no overrides.
  3. Percentage rollout — stable hash of user_id into 0..99 bucket;
     enabled when bucket < percentage.
"""

from meridian_feature_flags.decisions import FlagDecision, RolloutResult
from meridian_feature_flags.memory import InMemoryFeatureFlagStore
from meridian_feature_flags.postgres import PostgresFeatureFlagStore
from meridian_feature_flags.protocols import FeatureFlagStore
from meridian_feature_flags.rollout import (
    FeatureFlag,
    RolloutService,
    bucket_for_user,
)

__all__ = [
    "FeatureFlag",
    "FeatureFlagStore",
    "FlagDecision",
    "InMemoryFeatureFlagStore",
    "PostgresFeatureFlagStore",
    "RolloutResult",
    "RolloutService",
    "bucket_for_user",
]
