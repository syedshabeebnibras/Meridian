"""Operational primitives — Section 11.

- Error taxonomy: MeridianError subclasses with MERIDIAN-### codes
- Rate limiter: token-bucket per user, with in-memory impl for tests
"""

from meridian_ops.errors import (
    ClassificationError,
    GuardrailBlockedInputError,
    GuardrailBlockedOutputError,
    MeridianError,
    ProviderError,
    ProviderRateLimitedError,
    RetrievalError,
    TimeoutError,
    ToolError,
    ValidationFaithfulnessError,
    ValidationSchemaError,
)
from meridian_ops.rate_limit import (
    RateLimiter,
    RateLimitExceededError,
    RedisTokenBucketRateLimiter,
    TokenBucketRateLimiter,
)

__all__ = [
    "ClassificationError",
    "GuardrailBlockedInputError",
    "GuardrailBlockedOutputError",
    "MeridianError",
    "ProviderError",
    "ProviderRateLimitedError",
    "RateLimitExceededError",
    "RateLimiter",
    "RedisTokenBucketRateLimiter",
    "RetrievalError",
    "TimeoutError",
    "TokenBucketRateLimiter",
    "ToolError",
    "ValidationFaithfulnessError",
    "ValidationSchemaError",
]
