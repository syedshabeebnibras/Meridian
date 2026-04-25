"""Cost accounting — Section 7 §Cost controls + Section 11 §Cost Accounting dashboard.

- USD rate table per model
- CostAccountant computes per-request cost from ModelResponse.usage
- PerUserDailyTracker / RedisDailyTracker track per-(user|workspace) daily spend
- CostCircuitBreaker / WorkspaceCostBreaker block frontier when over budget
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
    WorkspaceCostBreaker,
)
from meridian_cost_accounting.tracker import (
    DailyTracker,
    PerUserDailyTracker,
    RedisDailyTracker,
    UserSpend,
)

__all__ = [
    "CostAccountant",
    "CostBreakdown",
    "CostBreakerOpenError",
    "CostBreakerState",
    "CostCircuitBreaker",
    "DailyTracker",
    "ModelRate",
    "PerUserDailyTracker",
    "RedisDailyTracker",
    "UserSpend",
    "WorkspaceCostBreaker",
    "default_rates",
]
