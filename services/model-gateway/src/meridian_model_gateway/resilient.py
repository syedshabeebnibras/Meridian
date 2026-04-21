"""Convenience factory that stacks CircuitBreaker(RetryingClient(LiteLLMClient))."""

from __future__ import annotations

from dataclasses import dataclass

from meridian_contracts import ModelRequest, ModelResponse

from meridian_model_gateway.circuit import CircuitBreaker
from meridian_model_gateway.client import LiteLLMClient, LiteLLMConfig
from meridian_model_gateway.protocols import ModelClient
from meridian_model_gateway.retry import RetryingClient, RetryPolicy


@dataclass
class ResilientClient:
    """Stacks retry + circuit breaker over a ModelClient."""

    inner: ModelClient

    def chat(self, request: ModelRequest) -> ModelResponse:
        return self.inner.chat(request)


def resilient_client(
    *,
    base: ModelClient | None = None,
    config: LiteLLMConfig | None = None,
    retry_policy: RetryPolicy | None = None,
    failure_threshold: int = 3,
    window_seconds: float = 60.0,
    cooldown_seconds: float = 30.0,
) -> ResilientClient:
    """Build the standard CircuitBreaker(Retry(LiteLLM(...))) stack.

    Pass ``base`` to inject a fake client for tests.
    """
    inner_client = base or LiteLLMClient(config or LiteLLMConfig.from_env())
    retrying = RetryingClient(inner=inner_client, policy=retry_policy or RetryPolicy())
    breaker = CircuitBreaker(
        inner=retrying,
        failure_threshold=failure_threshold,
        window_seconds=window_seconds,
        cooldown_seconds=cooldown_seconds,
    )
    return ResilientClient(inner=breaker)
