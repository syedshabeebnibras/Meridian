"""Per-key rate limiter — token bucket.

Two implementations behind a shared ``RateLimiter`` protocol:

  - ``TokenBucketRateLimiter``       — in-memory; single-process dev/test.
  - ``RedisTokenBucketRateLimiter``  — Redis-backed via atomic Lua, so
                                       multiple uvicorn workers / pods
                                       share one bucket per key.

Section 7 §Cost controls calls out per-user daily budgets; this module
adds short-term burst control. Phase 4 makes the limit *distributed* so
running ``--workers 4`` doesn't multiply the effective burst by 4.

Key composition is the caller's job. The orchestrator API layer composes
``f"{workspace_id}:{user_id}:{action}"`` so we can rate-limit per
(workspace, user, action) triple. Pass any string here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import redis

logger = logging.getLogger("meridian.rate_limit")


class RateLimitExceededError(RuntimeError):
    """Raised when a caller is over their configured rate limit."""


class RateLimiter(Protocol):
    """Pluggable rate limiter."""

    capacity: float
    refill_per_second: float

    def allow(self, key: str, *, cost: float = 1.0) -> None: ...


@dataclass
class _Bucket:
    tokens: float
    last_refill_ts: float


@dataclass
class TokenBucketRateLimiter:
    """In-memory token-bucket per-key limiter.

    Burst = ``capacity``; sustained rate = ``refill_per_second``.
    """

    capacity: float = 30.0
    refill_per_second: float = 1.0
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


# ---------------------------------------------------------------------------
# Redis-backed limiter (Phase 4)
# ---------------------------------------------------------------------------
# The whole bucket update happens inside one EVAL — Redis runs Lua scripts
# atomically, which is exactly the consistency guarantee we need so two
# concurrent workers can't both see ``tokens=1`` and both decrement.
#
# Storage shape: a hash per key with fields ``tokens`` (float) and ``ts``
# (server-local monotonic time, in seconds). TTL is 2x the time to refill
# from empty so abandoned buckets eventually evict.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed
if tokens < cost then
    allowed = 0
else
    allowed = 1
    tokens = tokens - cost
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)
return {allowed, tostring(tokens)}
"""


@dataclass
class RedisTokenBucketRateLimiter:
    """Distributed token-bucket limiter.

    A single Lua script does ``read → refill → check → decrement → write``
    atomically, so the bucket is consistent across uvicorn workers and pods.

    ``namespace`` prefixes every key (e.g. ``meridian:rl:``) so this limiter
    can share a Redis with the session store / semantic cache without
    colliding.
    """

    redis_client: redis.Redis
    capacity: float = 30.0
    refill_per_second: float = 1.0
    namespace: str = "meridian:rl:"
    clock: Callable[[], float] = field(default=lambda: __import__("time").time())
    _script: object | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        # ``register_script`` returns a Script callable that re-uses the same
        # SHA1 across calls — tiny perf win + saves a round-trip.
        self._script = self.redis_client.register_script(_TOKEN_BUCKET_LUA)

    def allow(self, key: str, *, cost: float = 1.0) -> None:
        # TTL must outlive the time it takes to refill the bucket from empty;
        # otherwise an idle key drops state and the next caller gets a fresh
        # full bucket. Two refill cycles is a safe ceiling.
        ttl = max(60, int(2 * self.capacity / max(self.refill_per_second, 0.001)))
        assert self._script is not None
        try:
            allowed, remaining = self._script(  # type: ignore[operator]
                keys=[f"{self.namespace}{key}"],
                args=[self.capacity, self.refill_per_second, self.clock(), cost, ttl],
            )
        except Exception as exc:
            # Fail-open: a Redis outage should not 5xx every request. Log and
            # let the call through — the orchestrator still has the cost
            # breaker as a second line of defence.
            logger.warning("redis rate limiter unavailable, failing open: %s", exc)
            return
        if int(allowed) == 0:
            raise RateLimitExceededError(
                f"rate limit exceeded for {key!r}: {float(remaining):.2f} < {cost:.2f}"
            )
