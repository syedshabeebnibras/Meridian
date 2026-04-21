"""Retry layer — Section 7 policy table.

| Scenario       | Max retries | Backoff                           |
|----------------|-------------|-----------------------------------|
| 429            | 3           | Exponential + jitter: 1s, 3s, 9s  |
| 5xx            | 2           | Exponential: 2s, 6s               |
| 4xx (non-429)  | 0           | n/a                               |
| timeout        | 1           | immediate                         |
| other          | 0           | n/a                               |

The retry layer is idempotent w.r.t. the caller — the input ModelRequest is
not mutated; only the metadata dict gets an `attempt` key stamped on it.
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


@dataclass
class RetryingClient:
    """Wraps an inner ModelClient with Section 7's retry policy."""

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
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status == 429:
                    delay = self._next_delay(attempt, self.policy.backoff_429)
                    if attempt - 1 >= self.policy.max_retries_429:
                        break
                    self.sleep(delay)
                    continue
                if 500 <= status < 600:
                    delay = self._next_delay(attempt, self.policy.backoff_5xx)
                    if attempt - 1 >= self.policy.max_retries_5xx:
                        break
                    self.sleep(delay)
                    continue
                # 4xx (non-429) — do not retry.
                break
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                delay = self._next_delay(attempt, self.policy.backoff_timeout)
                if attempt - 1 >= self.policy.max_retries_timeout:
                    break
                self.sleep(delay)
                continue
            except ModelDispatchError as exc:
                # Already wrapped by the LiteLLM client — don't double-retry.
                last_exc = exc
                break
        raise ModelDispatchError(f"LiteLLM call failed after {attempt} attempt(s)") from last_exc

    # ------------------------------------------------------------------
    def _next_delay(self, attempt: int, ladder: tuple[float, ...]) -> float:
        base = ladder[min(attempt - 1, len(ladder) - 1)]
        if self.policy.jitter_ratio <= 0:
            return base
        spread = base * self.policy.jitter_ratio
        return max(0.0, base + self.rng.uniform(-spread, spread))


def _stamp_attempt(request: ModelRequest, attempt: int) -> ModelRequest:
    """Return a new ModelRequest with `metadata.attempt` set.

    Idempotency key derivation (Section 7) is the caller's job; we only
    stamp the attempt number so provider logs and our traces line up.
    """
    new_metadata = dict(request.metadata)
    new_metadata["attempt"] = str(attempt)
    return request.model_copy(update={"metadata": new_metadata})
