"""CostCircuitBreaker — Section 7 + Section 11.

Fires when daily spend > 150% of the configured daily budget. When open,
the orchestrator degrades frontier requests to mid (or refuses if the
query requires frontier).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum


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
