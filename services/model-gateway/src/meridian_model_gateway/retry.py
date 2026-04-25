"""Retry layer — Section 7 policy table.

| Scenario       | Max retries | Backoff                           |
|----------------|-------------|-----------------------------------|
| 429            | 3           | Exponential + jitter: 1s, 3s, 9s  |
| 5xx            | 2           | Exponential: 2s, 6s               |
| 4xx (non-429)  | 0           | n/a                               |
| timeout        | 1           | immediate                         |
| other          | 0           | n/a                               |

The retry layer is idempotent w.r.t. the caller — the input ``ModelRequest`` is
not mutated; only the metadata dict gets an ``attempt`` key stamped on it.

Error sources
-------------
``RetryingClient`` handles two equivalent error shapes so tests and the real
stack exercise the same policy:

1. Raw ``httpx.HTTPStatusError`` / ``httpx.TimeoutException`` /
   ``httpx.ConnectError`` — used by unit tests that stub the inner client.
2. ``ModelDispatchError`` with typed ``status_code`` / ``retryable`` fields
   — emitted by ``LiteLLMClient`` in the real path.

Both reach the same decision tree: 429 ↦ 429 ladder, 5xx ↦ 5xx ladder,
transport ↦ timeout ladder, anything else ↦ no retry.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from meridian_contracts import ModelRequest, ModelResponse

from meridian_model_gateway.client import ModelDispatchError
from meridian_model_gateway.protocols import ModelClient


@dataclass(frozen=True)
class RetryPolicy:
    max_retries_429: int = 3
    max_retries_5xx: int = 2
    max_retries_timeout: int = 1
    backoff_429: tuple[float, ...] = (1.0, 3.0, 9.0)
    backoff_5xx: tuple[float, ...] = (2.0, 6.0)
    backoff_timeout: tuple[float, ...] = (0.5,)
    jitter_ratio: float = 0.25  # ±25% of the scheduled delay


# Internal tag for the retry decision produced by _classify_exception.
# - "429" / "5xx" / "timeout" pick the matching ladder
# - "none" means propagate the failure without retry
_RetryKind = str


@dataclass
class RetryingClient:
    """Wraps an inner ``ModelClient`` with Section 7's retry policy."""

    inner: ModelClient
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    sleep: Callable[[float], None] = time.sleep  # injectable for tests
    rng: random.Random = field(default_factory=random.Random)

    def chat(self, request: ModelRequest) -> ModelResponse:
        attempt = 0
        last_exc: Exception | None = None
        while True:
            attempt += 1
            stamped = _stamp_attempt(request, attempt)
            try:
                return self.inner.chat(stamped)
            except (
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.ConnectError,
                ModelDispatchError,
            ) as exc:
                last_exc = exc
                kind = _classify_exception(exc)
                if kind == "none":
                    break
                ladder, max_retries = self._ladder_for(kind)
                if attempt - 1 >= max_retries:
                    break
                self.sleep(self._next_delay(attempt, ladder))
                continue
        # Exhausted — surface a typed ModelDispatchError so downstream callers
        # (e.g. CircuitBreaker, orchestrator) can read status_code/retryable.
        if isinstance(last_exc, ModelDispatchError):
            raise last_exc
        raise _wrap_as_mde(last_exc, attempts=attempt)

    # ------------------------------------------------------------------
    def _ladder_for(self, kind: _RetryKind) -> tuple[tuple[float, ...], int]:
        if kind == "429":
            return self.policy.backoff_429, self.policy.max_retries_429
        if kind == "5xx":
            return self.policy.backoff_5xx, self.policy.max_retries_5xx
        # "timeout"
        return self.policy.backoff_timeout, self.policy.max_retries_timeout

    def _next_delay(self, attempt: int, ladder: tuple[float, ...]) -> float:
        base = ladder[min(attempt - 1, len(ladder) - 1)]
        if self.policy.jitter_ratio <= 0:
            return base
        spread = base * self.policy.jitter_ratio
        return max(0.0, base + self.rng.uniform(-spread, spread))


def _classify_exception(exc: Exception) -> _RetryKind:
    """Map an inner-client exception to a retry kind, or 'none'."""
    if isinstance(exc, ModelDispatchError):
        if not exc.retryable:
            return "none"
        status = exc.status_code
        if status == 429:
            return "429"
        if status is not None and 500 <= status < 600:
            return "5xx"
        if status is None:
            # Transport failure — use the timeout ladder.
            return "timeout"
        return "none"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return "429"
        if 500 <= status < 600:
            return "5xx"
        return "none"
    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError):
        return "timeout"
    return "none"


def _wrap_as_mde(exc: Exception | None, *, attempts: int) -> ModelDispatchError:
    """Final wrap after retries exhausted — keeps the typed contract intact."""
    if exc is None:
        return ModelDispatchError(
            f"LiteLLM call failed after {attempts} attempt(s): <no inner exception>",
            status_code=None,
            retryable=False,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        body = exc.response.text[:500] if exc.response is not None else ""
        return ModelDispatchError(
            f"LiteLLM call failed after {attempts} attempt(s): {status}",
            status_code=status,
            response_body=body,
            cause_type=type(exc).__name__,
        )
    return ModelDispatchError(
        f"LiteLLM call failed after {attempts} attempt(s) ({type(exc).__name__}): {exc}",
        status_code=None,
        retryable=False,
        cause_type=type(exc).__name__,
    )


def _stamp_attempt(request: ModelRequest, attempt: int) -> ModelRequest:
    """Return a new ``ModelRequest`` with ``metadata.attempt`` set.

    Idempotency key derivation (Section 7) is the caller's job; we only
    stamp the attempt number so provider logs and our traces line up.
    """
    new_metadata = dict(request.metadata)
    new_metadata["attempt"] = str(attempt)
    return request.model_copy(update={"metadata": new_metadata})
