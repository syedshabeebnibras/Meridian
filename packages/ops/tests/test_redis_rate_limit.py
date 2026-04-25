"""Phase 4 — distributed rate limiter tests against fakeredis.

Validates the property that *matters* for production: two limiter
instances pointed at the same Redis observe the same bucket. Without
that, scaling horizontally silently multiplies the effective burst.
"""

from __future__ import annotations

import itertools

import fakeredis
import pytest
from meridian_ops import RateLimitExceededError, RedisTokenBucketRateLimiter


def _frozen_clock() -> callable:  # type: ignore[valid-type]
    """Returns a clock callable whose time can be advanced manually."""
    state = {"t": 1_000.0}

    def now() -> float:
        return state["t"]

    now.advance = lambda secs: state.update(t=state["t"] + secs)  # type: ignore[attr-defined]
    return now


def test_redis_limiter_throttle_is_shared_across_instances() -> None:
    """Two limiters sharing one Redis must see one bucket per key."""
    server = fakeredis.FakeServer()
    a = RedisTokenBucketRateLimiter(
        redis_client=fakeredis.FakeRedis(server=server),
        capacity=3,
        refill_per_second=0.0,  # no refill — every allow burns a token
        clock=lambda: 1000.0,
    )
    b = RedisTokenBucketRateLimiter(
        redis_client=fakeredis.FakeRedis(server=server),
        capacity=3,
        refill_per_second=0.0,
        clock=lambda: 1000.0,
    )
    # 3 tokens across both limiters together.
    a.allow("ws1:u1:chat")
    b.allow("ws1:u1:chat")
    a.allow("ws1:u1:chat")
    with pytest.raises(RateLimitExceededError):
        b.allow("ws1:u1:chat")


def test_redis_limiter_refills_over_time() -> None:
    clock = _frozen_clock()
    limiter = RedisTokenBucketRateLimiter(
        redis_client=fakeredis.FakeRedis(),
        capacity=2,
        refill_per_second=1.0,
        clock=clock,  # type: ignore[arg-type]
    )
    limiter.allow("k")
    limiter.allow("k")
    with pytest.raises(RateLimitExceededError):
        limiter.allow("k")
    clock.advance(2)  # type: ignore[attr-defined]
    limiter.allow("k")
    limiter.allow("k")


def test_redis_limiter_keys_isolated() -> None:
    """Different (workspace, user, action) tuples don't leak into each other."""
    limiter = RedisTokenBucketRateLimiter(
        redis_client=fakeredis.FakeRedis(),
        capacity=1,
        refill_per_second=0.0,
        clock=lambda: 1000.0,
    )
    limiter.allow("ws1:u1:chat")
    limiter.allow("ws2:u1:chat")  # different workspace
    limiter.allow("ws1:u2:chat")  # different user
    limiter.allow("ws1:u1:upload")  # different action
    # Same key would now refuse.
    with pytest.raises(RateLimitExceededError):
        limiter.allow("ws1:u1:chat")


def test_redis_limiter_fails_open_when_redis_unreachable() -> None:
    """A Redis outage must NOT 5xx every request."""

    class _Broken:
        def register_script(self, _src: str) -> object:
            def _raise(*_a, **_kw):  # type: ignore[no-untyped-def]
                raise ConnectionError("redis down")

            return _raise

    limiter = RedisTokenBucketRateLimiter(
        redis_client=_Broken(),  # type: ignore[arg-type]
        capacity=1,
        refill_per_second=0.0,
    )
    # Should not raise, even past the burst limit.
    for _ in itertools.repeat(None, 5):
        limiter.allow("k")
