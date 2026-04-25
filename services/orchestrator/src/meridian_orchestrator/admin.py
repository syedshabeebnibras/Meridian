"""Admin override knobs for rate limiting + cost breakers.

Operators sometimes need to bypass per-workspace caps for an enterprise
customer or during an incident. This module is the single place where
those bypass decisions live so audit + tests can pin them down.

The override list is environment-driven so it can be flipped via a
restart without a code deploy:

    MERIDIAN_RATELIMIT_BYPASS_WORKSPACES=ws1,ws2
    MERIDIAN_BUDGET_BYPASS_WORKSPACES=ws1

Bypass is per-(scope, kind) — a workspace can be over its rate limit
budget without also being over its cost budget, and vice versa.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AdminOverride:
    """Read-only set of workspace IDs allowed to bypass each control."""

    rate_limit_bypass: frozenset[str] = field(default_factory=frozenset)
    budget_bypass: frozenset[str] = field(default_factory=frozenset)

    def rate_limit_exempt(self, workspace_id: str) -> bool:
        return workspace_id in self.rate_limit_bypass

    def budget_exempt(self, workspace_id: str) -> bool:
        return workspace_id in self.budget_bypass

    @classmethod
    def from_env(cls) -> AdminOverride:
        return cls(
            rate_limit_bypass=_parse_csv(
                os.environ.get("MERIDIAN_RATELIMIT_BYPASS_WORKSPACES", "")
            ),
            budget_bypass=_parse_csv(os.environ.get("MERIDIAN_BUDGET_BYPASS_WORKSPACES", "")),
        )


def _parse_csv(raw: str) -> frozenset[str]:
    return frozenset(x.strip() for x in raw.split(",") if x.strip())
