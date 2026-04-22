"""Error taxonomy + rate limiter tests."""

from __future__ import annotations

import pytest
from meridian_ops import (
    ClassificationError,
    GuardrailBlockedInputError,
    MeridianError,
    ProviderError,
    ProviderRateLimitedError,
    RateLimitExceededError,
    RetrievalError,
    TimeoutError,
    TokenBucketRateLimiter,
    ToolError,
    ValidationFaithfulnessError,
    ValidationSchemaError,
)


# ---- Error taxonomy ----------------------------------------------------
def test_every_error_has_unique_code() -> None:
    codes = {
        cls.code
        for cls in [
            GuardrailBlockedInputError,
            ClassificationError,
            RetrievalError,
            ProviderError,
            ProviderRateLimitedError,
            ValidationSchemaError,
            ValidationFaithfulnessError,
            ToolError,
            TimeoutError,
        ]
    }
    expected = {f"MERIDIAN-{n:03d}" for n in [1, 2, 3, 4, 5, 6, 7, 9, 10]}
    assert codes == expected


def test_error_str_includes_code() -> None:
    err = RetrievalError("RAG timeout")
    assert "[MERIDIAN-003]" in str(err)
    assert "RAG timeout" in str(err)


def test_retryable_flags_match_section_11() -> None:
    assert RetrievalError.retryable is True
    assert ProviderRateLimitedError.retryable is True
    assert ValidationSchemaError.retryable is True  # 1 corrective retry
    assert ValidationFaithfulnessError.retryable is False
    assert GuardrailBlockedInputError.retryable is False


def test_all_errors_are_meridian_errors() -> None:
    for cls in [
        ClassificationError,
        RetrievalError,
        ProviderError,
        ToolError,
    ]:
        assert issubclass(cls, MeridianError)


# ---- Token bucket ------------------------------------------------------
class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_allows_up_to_capacity() -> None:
    clock = _FakeClock()
    limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=1.0, clock=clock)
    for _ in range(5):
        limiter.allow("user_a")
    with pytest.raises(RateLimitExceededError):
        limiter.allow("user_a")


def test_refills_over_time() -> None:
    clock = _FakeClock()
    limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=1.0, clock=clock)
    for _ in range(5):
        limiter.allow("user_a")
    clock.t = 3.0  # refill 3 tokens
    for _ in range(3):
        limiter.allow("user_a")
    with pytest.raises(RateLimitExceededError):
        limiter.allow("user_a")


def test_keys_are_isolated() -> None:
    clock = _FakeClock()
    limiter = TokenBucketRateLimiter(capacity=2, refill_per_second=1.0, clock=clock)
    limiter.allow("user_a")
    limiter.allow("user_a")
    with pytest.raises(RateLimitExceededError):
        limiter.allow("user_a")
    # Different user starts fresh.
    limiter.allow("user_b")
    limiter.allow("user_b")


def test_remaining_reports_current_tokens() -> None:
    clock = _FakeClock()
    limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=1.0, clock=clock)
    assert limiter.remaining("user_a") == 5
    limiter.allow("user_a")
    assert limiter.remaining("user_a") == 4
