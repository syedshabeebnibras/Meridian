"""Typed decision result. The orchestrator checks `allowed` and, if False,
returns the configured refusal message."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RolloutResult(StrEnum):
    KILL_SWITCH = "kill_switch"
    ALLOWLISTED = "allowlisted"
    DENYLISTED = "denylisted"
    IN_ROLLOUT = "in_rollout"
    OUT_OF_ROLLOUT = "out_of_rollout"
    FLAG_MISSING = "flag_missing"


class FlagDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    result: RolloutResult
    bucket: int | None = None  # user's 0..99 bucket when percentage check ran
    percentage: int | None = None
