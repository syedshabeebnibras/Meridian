"""Meridian model gateway.

Layered on top of LiteLLM:

  LiteLLMClient            — raw HTTP call to /v1/chat/completions.
  RetryingClient           — Section 7 retry policy (429/5xx, exp-backoff + jitter).
  CircuitBreaker           — Section 7 circuit breaker (3 failures/60s → open).
  resilient_client()       — convenience factory that stacks the three.

The Protocol (ModelClient) stays the same at every layer, so callers can
compose freely.
"""

from meridian_model_gateway.circuit import CircuitBreaker, CircuitOpenError
from meridian_model_gateway.client import LiteLLMClient, LiteLLMConfig, ModelDispatchError
from meridian_model_gateway.protocols import ModelClient
from meridian_model_gateway.resilient import ResilientClient, resilient_client
from meridian_model_gateway.retry import RetryingClient, RetryPolicy

__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "LiteLLMClient",
    "LiteLLMConfig",
    "ModelClient",
    "ModelDispatchError",
    "ResilientClient",
    "RetryPolicy",
    "RetryingClient",
    "resilient_client",
]
