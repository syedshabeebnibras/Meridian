"""Cost accounting + daily tracker + circuit breaker tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from meridian_contracts import ModelResponse, ModelUsage
from meridian_cost_accounting import (
    CostAccountant,
    CostBreakerOpenError,
    CostCircuitBreaker,
    PerUserDailyTracker,
)


def _response(model: str, in_tokens: int, out_tokens: int, cache_read: int = 0) -> ModelResponse:
    return ModelResponse(
        id="r",
        model=model,
        content={},
        usage=ModelUsage(
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cache_read_input_tokens=cache_read,
        ),
        latency_ms=1,
    )


def test_mid_tier_cost_matches_rate() -> None:
    acct = CostAccountant()
    breakdown = acct.cost_of(_response("meridian-mid", 1000, 500))
    assert breakdown.total_usd == Decimal("0.003") + Decimal("0.0075")


def test_cache_read_charged_at_reduced_rate() -> None:
    acct = CostAccountant()
    breakdown = acct.cost_of(_response("meridian-mid", 0, 0, cache_read=1_000_000))
    assert breakdown.cache_read_usd == Decimal("0.30")


def test_unknown_model_returns_zero() -> None:
    acct = CostAccountant()
    breakdown = acct.cost_of(_response("some-unknown-model", 1000, 500))
    assert breakdown.total_usd == Decimal("0")
    assert breakdown.model == "some-unknown-model"


def test_small_tier_is_cheap() -> None:
    acct = CostAccountant()
    mid = acct.cost_of(_response("meridian-mid", 1000, 500)).total_usd
    small = acct.cost_of(_response("meridian-small", 1000, 500)).total_usd
    assert small < mid


def test_tracker_sums_per_user_per_day() -> None:
    tracker = PerUserDailyTracker()
    tracker.record("u1", Decimal("0.01"))
    tracker.record("u1", Decimal("0.02"))
    tracker.record("u2", Decimal("0.05"))
    assert tracker.today("u1").total_usd == Decimal("0.03")
    assert tracker.today("u1").request_count == 2
    assert tracker.today("u2").total_usd == Decimal("0.05")


def test_tracker_isolates_days() -> None:
    now = datetime.now(tz=UTC)
    pretend_today = now

    def clock() -> datetime:
        return pretend_today

    tracker = PerUserDailyTracker(clock=clock)
    tracker.record("u1", Decimal("0.10"))
    assert tracker.today("u1").total_usd == Decimal("0.10")

    pretend_today = now + timedelta(days=1)
    assert tracker.today("u1").total_usd == Decimal("0")


def test_breaker_closed_under_budget() -> None:
    breaker = CostCircuitBreaker(daily_budget_usd=Decimal("100"))
    breaker.record(Decimal("50"))
    assert breaker.state.value == "closed"
    breaker.check_frontier_allowed()


def test_breaker_opens_above_150_percent() -> None:
    breaker = CostCircuitBreaker(daily_budget_usd=Decimal("100"))
    breaker.record(Decimal("160"))
    assert breaker.state.value == "open"
    with pytest.raises(CostBreakerOpenError):
        breaker.check_frontier_allowed()


def test_breaker_resets_across_day_boundary() -> None:
    now = datetime.now(tz=UTC)
    current = now

    def clock() -> datetime:
        return current

    breaker = CostCircuitBreaker(daily_budget_usd=Decimal("100"), clock=clock)
    breaker.record(Decimal("200"))
    assert breaker.state.value == "open"
    current = now + timedelta(days=1)
    assert breaker.spend_today == Decimal("0")
    breaker.record(Decimal("10"))
    assert breaker.state.value == "closed"
