"""Phase 4 — Redis-backed daily tracker + per-workspace cost breaker."""

from __future__ import annotations

from decimal import Decimal

import fakeredis
import pytest
from meridian_cost_accounting import (
    CostBreakerOpenError,
    CostBreakerState,
    PerUserDailyTracker,
    RedisDailyTracker,
    WorkspaceCostBreaker,
)


def test_redis_daily_tracker_accumulates_across_clients() -> None:
    """Two trackers sharing one Redis must see one running total per (scope, day)."""
    server = fakeredis.FakeServer()
    a = RedisDailyTracker(redis_client=fakeredis.FakeRedis(server=server))
    b = RedisDailyTracker(redis_client=fakeredis.FakeRedis(server=server))
    a.record("ws1", Decimal("0.50"))
    b.record("ws1", Decimal("0.25"))
    snapshot = a.today("ws1")
    assert snapshot.total_usd == Decimal("0.75")
    assert snapshot.request_count == 2


def test_redis_daily_tracker_isolates_scopes() -> None:
    tracker = RedisDailyTracker(redis_client=fakeredis.FakeRedis())
    # Use floats that round-trip exactly through float64 so we can assert
    # equality. HINCRBYFLOAT goes through C double — 0.10 doesn't, 0.125 does.
    tracker.record("ws1", Decimal("1"))
    tracker.record("ws2", Decimal("0.125"))
    assert tracker.today("ws1").total_usd == Decimal("1")
    assert tracker.today("ws2").total_usd == Decimal("0.125")
    assert tracker.today("ws3").total_usd == Decimal("0")


def test_workspace_breaker_opens_above_overrun_ratio() -> None:
    tracker = PerUserDailyTracker()
    breaker = WorkspaceCostBreaker(
        tracker=tracker,
        daily_budget_usd=Decimal("10"),
        overrun_ratio=Decimal("1.5"),
    )
    tracker.record("ws1", Decimal("14"))  # under 1.5x → still closed
    assert breaker.state_for("ws1") is CostBreakerState.CLOSED
    tracker.record("ws1", Decimal("2"))  # 16 > 15 → opens
    assert breaker.state_for("ws1") is CostBreakerState.OPEN
    with pytest.raises(CostBreakerOpenError):
        breaker.check_frontier_allowed("ws1")


def test_workspace_breaker_isolates_workspaces() -> None:
    """Workspace A blowing its budget must not trip workspace B's breaker."""
    tracker = PerUserDailyTracker()
    breaker = WorkspaceCostBreaker(tracker=tracker, daily_budget_usd=Decimal("1"))
    tracker.record("wsA", Decimal("100"))
    assert breaker.state_for("wsA") is CostBreakerState.OPEN
    assert breaker.state_for("wsB") is CostBreakerState.CLOSED


def test_workspace_breaker_with_redis_tracker() -> None:
    """End-to-end: distributed tracker drives the breaker."""
    tracker = RedisDailyTracker(redis_client=fakeredis.FakeRedis())
    breaker = WorkspaceCostBreaker(tracker=tracker, daily_budget_usd=Decimal("5"))
    assert breaker.state_for("ws1") is CostBreakerState.CLOSED
    tracker.record("ws1", Decimal("10"))  # > 1.5x of 5
    assert breaker.state_for("ws1") is CostBreakerState.OPEN
