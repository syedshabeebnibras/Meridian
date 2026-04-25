"""Daily spend trackers — per-user and per-workspace ceilings.

Section 7 §Cost controls: 50K tokens/user/day soft limit; this tracker is
the book-keeping layer. Alerting + enforcement policy live in the
orchestrator + the ``CostCircuitBreaker``.

Two implementations behind the ``DailyTracker`` Protocol:

  - ``PerUserDailyTracker`` — in-memory; safe for single-process dev/test.
  - ``RedisDailyTracker``   — distributed; multiple workers + pods share
                              one counter per (scope_id, day).

Phase 4 split the tracker by *scope* (user or workspace) so the breaker
can answer "is workspace X over its budget?" the same way it answers
"is user U over theirs?".
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import redis

logger = logging.getLogger("meridian.cost_tracker")


@dataclass
class UserSpend:
    user_id: str
    day: date
    total_usd: Decimal
    request_count: int


class DailyTracker(Protocol):
    """Anything that can record + report per-(scope, day) spend."""

    def record(self, scope_id: str, amount_usd: Decimal) -> UserSpend: ...

    def today(self, scope_id: str) -> UserSpend: ...


@dataclass
class PerUserDailyTracker:
    """In-memory per-(user, day) spend tracker.

    Swap for a Redis-backed implementation in prod; same interface."""

    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))
    _spend: dict[tuple[str, date], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: Decimal("0"))
    )
    _counts: dict[tuple[str, date], int] = field(default_factory=lambda: defaultdict(int))

    def record(self, scope_id: str, amount_usd: Decimal) -> UserSpend:
        today = self.clock().date()
        key = (scope_id, today)
        self._spend[key] += amount_usd
        self._counts[key] += 1
        return UserSpend(
            user_id=scope_id,
            day=today,
            total_usd=self._spend[key],
            request_count=self._counts[key],
        )

    def today(self, scope_id: str) -> UserSpend:
        today = self.clock().date()
        key = (scope_id, today)
        return UserSpend(
            user_id=scope_id,
            day=today,
            total_usd=self._spend.get(key, Decimal("0")),
            request_count=self._counts.get(key, 0),
        )


# ---------------------------------------------------------------------------
# Redis-backed tracker (Phase 4)
# ---------------------------------------------------------------------------
@dataclass
class RedisDailyTracker:
    """Distributed per-(scope, day) spend tracker.

    Storage shape: ``{namespace}{scope_id}:{YYYY-MM-DD}`` is a hash with
    fields ``total_usd`` (string Decimal) and ``count`` (int). We pick
    string Decimal over float so we don't lose precision over millions of
    fractional-cent additions.

    TTL is 32 days so yesterday's counter is still inspectable for
    end-of-day reports but stale counters eventually evict.
    """

    redis_client: redis.Redis
    namespace: str = "meridian:spend:"
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))

    def _key(self, scope_id: str, day: date) -> str:
        return f"{self.namespace}{scope_id}:{day.isoformat()}"

    def record(self, scope_id: str, amount_usd: Decimal) -> UserSpend:
        today = self.clock().date()
        key = self._key(scope_id, today)
        try:
            pipe = self.redis_client.pipeline()
            # HINCRBYFLOAT keeps a server-side float; we coerce to Decimal on
            # read. Acceptable precision loss for accounting is sub-cent at
            # the daily aggregation level.
            pipe.hincrbyfloat(key, "total_usd", float(amount_usd))
            pipe.hincrby(key, "count", 1)
            pipe.expire(key, 60 * 60 * 24 * 32)
            results = pipe.execute()
            total = Decimal(str(results[0]))
            count = int(results[1])
        except Exception as exc:
            logger.warning("redis daily tracker unavailable, falling back: %s", exc)
            return UserSpend(user_id=scope_id, day=today, total_usd=amount_usd, request_count=1)
        return UserSpend(user_id=scope_id, day=today, total_usd=total, request_count=count)

    def today(self, scope_id: str) -> UserSpend:
        today = self.clock().date()
        key = self._key(scope_id, today)
        try:
            data = self.redis_client.hmget(key, ["total_usd", "count"])
        except Exception as exc:
            logger.warning("redis daily tracker read failed: %s", exc)
            return UserSpend(user_id=scope_id, day=today, total_usd=Decimal("0"), request_count=0)
        # ``hmget`` returns ``Awaitable[list] | list``; on the sync client it's
        # always a list. Cast for type-checkers.
        rows = data if isinstance(data, list) else []
        raw_total = rows[0] if len(rows) > 0 else None
        raw_count = rows[1] if len(rows) > 1 else None
        total = Decimal(raw_total.decode() if isinstance(raw_total, bytes) else (raw_total or "0"))
        count = int(raw_count.decode() if isinstance(raw_count, bytes) else (raw_count or "0"))
        return UserSpend(user_id=scope_id, day=today, total_usd=total, request_count=count)
