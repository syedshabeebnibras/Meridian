"""Cost accounting — Section 7 §Cost controls + Section 11 §Cost Accounting dashboard.

- USD rate table per model
- CostAccountant computes per-request cost from ModelResponse.usage
- PerUserDailyTracker tracks per-user daily spend (in-memory)
- CostCircuitBreaker blocks frontier requests when daily spend > 150% budget
"""

from meridian_cost_accounting.accountant import (
    CostAccountant,
    CostBreakdown,
    ModelRate,
    default_rates,
)
from meridian_cost_accounting.breaker import (
    CostBreakerOpenError,
    CostBreakerState,
    CostCircuitBreaker,
)
from meridian_cost_accounting.tracker import PerUserDailyTracker, UserSpend

__all__ = [
    "CostAccountant",
    "CostBreakdown",
    "CostBreakerOpenError",
    "CostBreakerState",
    "CostCircuitBreaker",
    "ModelRate",
    "PerUserDailyTracker",
    "UserSpend",
    "default_rates",
]
