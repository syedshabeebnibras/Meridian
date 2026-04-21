"""Circuit breaker — Section 7 provider protection.

CLOSED  → normal service; failures counted against a rolling window
          (3 failures in 60s) and escalate to OPEN.
OPEN    → reject every call for the cooldown window (30s).
HALF_OPEN → the first call after cooldown probes; success → CLOSED,
          failure → OPEN again.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from meridian_contracts import ModelRequest, ModelResponse

from meridian_model_gateway.protocols import ModelClient


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the circuit is open and a call is rejected."""


@dataclass
class CircuitBreaker:
    """Wraps a ModelClient and drops calls when the provider looks unhealthy.

    Parameters mirror Section 7 defaults. `clock` is injected so tests can
    fast-forward time.
    """

    inner: ModelClient
    failure_threshold: int = 3
    window_seconds: float = 60.0
    cooldown_seconds: float = 30.0
    clock: Callable[[], float] = time.monotonic

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: deque[float] = field(default_factory=deque, init=False)
    _opened_at: float | None = field(default=None, init=False)

    # ------------------------------------------------------------------
    # ModelClient protocol
    # ------------------------------------------------------------------
    def chat(self, request: ModelRequest) -> ModelResponse:
        now = self.clock()
        self._reconcile_state(now)
        if self._state is CircuitState.OPEN:
            raise CircuitOpenError(
                f"circuit open since {self._opened_at:.1f}; cooldown {self.cooldown_seconds:.0f}s"
            )
        try:
            response = self.inner.chat(request)
        except Exception:
            self._record_failure(now)
            raise
        else:
            self._record_success(now)
            return response

    # ------------------------------------------------------------------
    # Inspection helpers (useful for tests + ops dashboards)
    # ------------------------------------------------------------------
    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def recent_failures(self) -> int:
        return len(self._failures)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _reconcile_state(self, now: float) -> None:
        # Drop failures outside the rolling window.
        cutoff = now - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

        if (
            self._state is CircuitState.OPEN
            and self._opened_at is not None
            and now - self._opened_at >= self.cooldown_seconds
        ):
            self._state = CircuitState.HALF_OPEN

    def _record_failure(self, now: float) -> None:
        if self._state is CircuitState.HALF_OPEN:
            # The probe failed — back to OPEN with a fresh cooldown.
            self._state = CircuitState.OPEN
            self._opened_at = now
            return
        self._failures.append(now)
        if len(self._failures) >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = now

    def _record_success(self, now: float) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failures.clear()
            self._opened_at = None
