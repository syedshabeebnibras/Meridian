"""Per-user rate limiter — token bucket.

Section 7 §Cost controls calls out per-user daily budgets; this module
adds short-term burst control on top. In prod the caller plugs a Redis
token bucket into the same interface; the in-memory version is here so
tests + single-process dev don't need Redis.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class RateLimitExceededError(RuntimeError):
    """Raised when a user is over their configured rate limit."""


@dataclass
class _Bucket:
    tokens: float
    last_refill_ts: float


@dataclass
class TokenBucketRateLimiter:
    """Token-bucket per-key rate limiter.

    `capacity` = maximum burst (tokens); `refill_per_second` = sustained rate.
    """

    capacity: float = 30.0  # 30 requests burst
    refill_per_second: float = 1.0  # 1 req/s sustained
    clock: Callable[[], float] = field(default=lambda: __import__("time").monotonic())
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, key: str, *, cost: float = 1.0) -> None:
        now = self.clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=self.capacity, last_refill_ts=now)
            self._buckets[key] = bucket

        elapsed = max(0.0, now - bucket.last_refill_ts)
        bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
        bucket.last_refill_ts = now

        if bucket.tokens < cost:
            raise RateLimitExceededError(
                f"rate limit exceeded for {key!r}: {bucket.tokens:.2f} < {cost:.2f}"
            )
        bucket.tokens -= cost

    def remaining(self, key: str) -> float:
        bucket = self._buckets.get(key)
        if bucket is None:
            return self.capacity
        now = self.clock()
        elapsed = max(0.0, now - bucket.last_refill_ts)
        return min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
