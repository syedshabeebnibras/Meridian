"""PerUserDailyTracker — per-user spend ceiling.

Section 7 §Cost controls: 50K tokens/user/day soft limit; this tracker is
the book-keeping layer. Alerting + enforcement policy live in the
orchestrator + the CostCircuitBreaker.

Redis-backed tracker is a drop-in; the in-memory implementation is here so
tests don't need Redis.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal


@dataclass
class UserSpend:
    user_id: str
    day: date
    total_usd: Decimal
    request_count: int


@dataclass
class PerUserDailyTracker:
    """In-memory per-(user, day) spend tracker.

    Swap for a Redis-backed implementation in prod; same interface."""

    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))
    _spend: dict[tuple[str, date], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: Decimal("0"))
    )
    _counts: dict[tuple[str, date], int] = field(default_factory=lambda: defaultdict(int))

    def record(self, user_id: str, amount_usd: Decimal) -> UserSpend:
        today = self.clock().date()
        key = (user_id, today)
        self._spend[key] += amount_usd
        self._counts[key] += 1
        return UserSpend(
            user_id=user_id,
            day=today,
            total_usd=self._spend[key],
            request_count=self._counts[key],
        )

    def today(self, user_id: str) -> UserSpend:
        today = self.clock().date()
        key = (user_id, today)
        return UserSpend(
            user_id=user_id,
            day=today,
            total_usd=self._spend.get(key, Decimal("0")),
            request_count=self._counts.get(key, 0),
        )
