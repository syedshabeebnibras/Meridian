"""Rollout logic — percentage via stable hash + allowlist + kill switch."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from meridian_feature_flags.decisions import FlagDecision, RolloutResult
from meridian_feature_flags.protocols import FeatureFlagStore


class FeatureFlag(BaseModel):
    """One rollout flag — the only "flag" Meridian v1 needs is `meridian.enabled`."""

    model_config = ConfigDict(extra="forbid")

    name: str
    percentage: int = Field(ge=0, le=100, default=0)
    kill_switch: bool = False
    allowlist: list[str] = Field(default_factory=list)
    denylist: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_by: str = "system"


def bucket_for_user(user_id: str, *, flag_name: str = "") -> int:
    """Map a user_id to a stable 0..99 bucket.

    Including `flag_name` in the hash means a user in the 40th percentile
    for one flag won't be in the same percentile for another — avoiding
    correlation across independent rollouts.
    """
    payload = f"{flag_name}::{user_id}".encode()
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], "big") % 100


@dataclass
class RolloutService:
    """Wraps a FeatureFlagStore with the Section-12 rollout decision logic."""

    store: FeatureFlagStore

    def evaluate(self, flag_name: str, user_id: str) -> FlagDecision:
        flag = self.store.get(flag_name)
        if flag is None:
            return FlagDecision(allowed=False, result=RolloutResult.FLAG_MISSING)
        if flag.kill_switch:
            return FlagDecision(allowed=False, result=RolloutResult.KILL_SWITCH)
        if user_id in flag.denylist:
            return FlagDecision(allowed=False, result=RolloutResult.DENYLISTED)
        if user_id in flag.allowlist:
            return FlagDecision(allowed=True, result=RolloutResult.ALLOWLISTED)
        bucket = bucket_for_user(user_id, flag_name=flag_name)
        if bucket < flag.percentage:
            return FlagDecision(
                allowed=True,
                result=RolloutResult.IN_ROLLOUT,
                bucket=bucket,
                percentage=flag.percentage,
            )
        return FlagDecision(
            allowed=False,
            result=RolloutResult.OUT_OF_ROLLOUT,
            bucket=bucket,
            percentage=flag.percentage,
        )
