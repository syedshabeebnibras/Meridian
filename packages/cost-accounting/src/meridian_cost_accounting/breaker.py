"""CostCircuitBreaker — Section 7 + Section 11.

Fires when daily spend > 150% of the configured daily budget. When open,
the orchestrator degrades frontier requests to mid (or refuses if the
query requires frontier).

Two flavours:

  - ``CostCircuitBreaker``           — global daily budget, in-process
                                       counter (legacy single-worker
                                       behaviour).
  - ``WorkspaceCostBreaker``         — per-workspace daily budget,
                                       backed by a ``DailyTracker`` so the
                                       counter is consistent across
                                       workers. Pass a ``RedisDailyTracker``
                                       to make it distributed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from meridian_cost_accounting.tracker import DailyTracker


class CostBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"


class CostBreakerOpenError(RuntimeError):
    """Raised when a frontier-tier request is attempted while the breaker is open."""


@dataclass
class CostCircuitBreaker:
    daily_budget_usd: Decimal
    overrun_ratio: Decimal = field(default=Decimal("1.5"))
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))
    _spend_today: Decimal = field(default=Decimal("0"), init=False)
    _day: date | None = field(default=None, init=False)

    def record(self, amount_usd: Decimal) -> None:
        today = self.clock().date()
        if self._day != today:
            self._day = today
            self._spend_today = Decimal("0")
        self._spend_today += amount_usd

    @property
    def state(self) -> CostBreakerState:
        threshold = self.daily_budget_usd * self.overrun_ratio
        return CostBreakerState.OPEN if self._spend_today > threshold else CostBreakerState.CLOSED

    @property
    def spend_today(self) -> Decimal:
        today = self.clock().date()
        if self._day != today:
            return Decimal("0")
        return self._spend_today

    def check_frontier_allowed(self) -> None:
        """Raise CostBreakerOpenError if frontier requests should be blocked."""
        if self.state is CostBreakerState.OPEN:
            raise CostBreakerOpenError(
                f"daily spend {self._spend_today:.4f} > "
                f"{self.daily_budget_usd * self.overrun_ratio:.4f} budget; "
                "frontier requests degraded until midnight UTC"
            )


# ---------------------------------------------------------------------------
# WorkspaceCostBreaker — per-workspace, distributed via DailyTracker
# ---------------------------------------------------------------------------
@dataclass
class WorkspaceCostBreaker:
    """Per-workspace breaker keyed off a shared ``DailyTracker``.

    The legacy ``CostCircuitBreaker`` keeps an in-process counter that's
    inaccurate under uvicorn ``--workers >1``. This breaker delegates every
    read to the tracker so two replicas observe the same total.

    Pair with ``RedisDailyTracker`` for production; pair with the in-memory
    ``PerUserDailyTracker`` for tests.
    """

    tracker: DailyTracker
    daily_budget_usd: Decimal
    overrun_ratio: Decimal = field(default=Decimal("1.5"))

    def state_for(self, workspace_id: str) -> CostBreakerState:
        spend = self.tracker.today(workspace_id).total_usd
        threshold = self.daily_budget_usd * self.overrun_ratio
        return CostBreakerState.OPEN if spend > threshold else CostBreakerState.CLOSED

    def is_over_budget(self, workspace_id: str) -> bool:
        """``True`` when the *raw* daily budget is exceeded (before the
        overrun ratio). Used to refuse non-degradable requests outright."""
        spend = self.tracker.today(workspace_id).total_usd
        return spend > self.daily_budget_usd

    def check_frontier_allowed(self, workspace_id: str) -> None:
        if self.state_for(workspace_id) is CostBreakerState.OPEN:
            raise CostBreakerOpenError(
                f"workspace {workspace_id!r} daily spend exceeds "
                f"{self.daily_budget_usd * self.overrun_ratio:.4f} budget; "
                "frontier requests degraded until midnight UTC"
            )
