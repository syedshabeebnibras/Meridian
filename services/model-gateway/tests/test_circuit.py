"""CircuitBreaker tests — exercise CLOSED → OPEN → HALF_OPEN transitions."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from meridian_contracts import ModelRequest, ModelResponse, ModelUsage
from meridian_model_gateway import CircuitBreaker, CircuitOpenError


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def tick(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


class _ScriptedClient:
    def __init__(self, outcomes: list[Callable[[ModelRequest], ModelResponse]]) -> None:
        self._outcomes = outcomes
        self.calls: list[ModelRequest] = []

    def chat(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return self._outcomes.pop(0)(request)


def _ok(request: ModelRequest) -> ModelResponse:
    return ModelResponse(
        id="ok",
        model=request.model,
        content={"ok": True},
        usage=ModelUsage(input_tokens=0, output_tokens=0),
        latency_ms=1,
    )


def _boom(_: ModelRequest) -> ModelResponse:
    raise RuntimeError("upstream exploded")


def _request() -> ModelRequest:
    return ModelRequest(
        model="meridian-mid",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=16,
    )


def test_closed_to_open_after_threshold() -> None:
    clock = _FakeClock()
    inner = _ScriptedClient([_boom, _boom, _boom])
    breaker = CircuitBreaker(
        inner=inner,  # type: ignore[arg-type]
        failure_threshold=3,
        window_seconds=60.0,
        cooldown_seconds=30.0,
        clock=clock,
    )
    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.chat(_request())
    assert breaker.state.value == "open"


def test_open_rejects_calls_fast() -> None:
    clock = _FakeClock()
    inner = _ScriptedClient([_boom, _boom, _boom])
    breaker = CircuitBreaker(
        inner=inner,  # type: ignore[arg-type]
        failure_threshold=3,
        clock=clock,
    )
    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.chat(_request())
    assert breaker.state.value == "open"

    # Subsequent call short-circuits — inner is NOT invoked.
    with pytest.raises(CircuitOpenError):
        breaker.chat(_request())
    assert len(inner.calls) == 3


def test_half_open_closes_on_success() -> None:
    clock = _FakeClock()
    # 3 failures to open, then a success for the probe.
    inner = _ScriptedClient([_boom, _boom, _boom, _ok])
    breaker = CircuitBreaker(
        inner=inner,  # type: ignore[arg-type]
        failure_threshold=3,
        window_seconds=60.0,
        cooldown_seconds=30.0,
        clock=clock,
    )
    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.chat(_request())

    # Advance past the cooldown.
    clock.tick(31.0)
    breaker.chat(_request())  # succeeds → CLOSED
    assert breaker.state.value == "closed"
    assert breaker.recent_failures == 0


def test_half_open_reopens_on_failure() -> None:
    clock = _FakeClock()
    inner = _ScriptedClient([_boom, _boom, _boom, _boom])
    breaker = CircuitBreaker(
        inner=inner,  # type: ignore[arg-type]
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=clock,
    )
    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.chat(_request())

    clock.tick(31.0)
    with pytest.raises(RuntimeError):
        breaker.chat(_request())
    assert breaker.state.value == "open"


def test_failures_outside_window_are_forgotten() -> None:
    clock = _FakeClock()
    inner = _ScriptedClient([_boom, _boom, _ok, _boom])
    breaker = CircuitBreaker(
        inner=inner,  # type: ignore[arg-type]
        failure_threshold=3,
        window_seconds=10.0,
        clock=clock,
    )
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.chat(_request())
    # Advance past the 10s window so earlier failures drop out.
    clock.tick(20.0)
    breaker.chat(_request())  # succeeds; state still CLOSED

    # A single new failure should NOT open the circuit.
    with pytest.raises(RuntimeError):
        breaker.chat(_request())
    assert breaker.state.value == "closed"
