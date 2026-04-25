"""Integration tests for the real gateway stack.

The unit tests in ``test_retry.py`` stub the inner client with a recorder
that raises ``httpx.HTTPStatusError`` directly. That misses the exact bug
this file covers: in production ``LiteLLMClient`` wraps every httpx
failure into a ``ModelDispatchError`` before it reaches ``RetryingClient``.

These tests drive real HTTP traffic through ``LiteLLMClient`` via
``httpx.MockTransport`` and verify the retry + circuit-breaker stack
actually replays 429/5xx/timeout in the shipped code path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest
from meridian_contracts import ModelRequest
from meridian_model_gateway import (
    CircuitBreaker,
    CircuitOpenError,
    LiteLLMClient,
    LiteLLMConfig,
    ModelDispatchError,
    RetryingClient,
    RetryPolicy,
)


@dataclass
class _ScriptedTransport(httpx.BaseTransport):
    """httpx transport that plays back a queue of responses/exceptions."""

    responses: list[httpx.Response | Exception]
    calls: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if not self.responses:
            raise AssertionError("scripted transport ran out of responses")
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "cmpl-1",
            "model": "meridian-mid",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )


def _status(code: int, body: str = '{"error":"x"}') -> httpx.Response:
    return httpx.Response(code, content=body.encode())


def _make_request() -> ModelRequest:
    return ModelRequest(
        model="meridian-mid",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64,
    )


def _sleep_tracker() -> tuple[Callable[[float], None], list[float]]:
    calls: list[float] = []
    return calls.append, calls


def _client(transport: _ScriptedTransport) -> LiteLLMClient:
    return LiteLLMClient(
        LiteLLMConfig(base_url="http://test", api_key="sk-test"), transport=transport
    )


# ---------------------------------------------------------------------------
# 1. 429 retries all the way through the shipped stack
# ---------------------------------------------------------------------------
def test_429_retries_through_real_stack() -> None:
    transport = _ScriptedTransport([_status(429), _status(429), _ok_response()])
    sleep_calls, sleeps = _sleep_tracker()
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=sleep_calls,
    )
    response = retrying.chat(_make_request())
    assert transport.calls == 3
    assert response.id == "cmpl-1"
    assert sleeps == [1.0, 3.0]


def test_429_exhausts_after_max_retries_real_stack() -> None:
    transport = _ScriptedTransport([_status(429)] * 4)
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    with pytest.raises(ModelDispatchError) as excinfo:
        retrying.chat(_make_request())
    # Typed MDE surfaces upstream status for callers.
    assert excinfo.value.status_code == 429
    assert excinfo.value.retryable is True
    # 1 original + 3 retries = 4 attempts.
    assert transport.calls == 4


# ---------------------------------------------------------------------------
# 2. 5xx retries through the real stack
# ---------------------------------------------------------------------------
def test_503_retries_through_real_stack() -> None:
    transport = _ScriptedTransport([_status(503), _ok_response()])
    sleep_calls, sleeps = _sleep_tracker()
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=sleep_calls,
    )
    response = retrying.chat(_make_request())
    assert response.id == "cmpl-1"
    assert sleeps == [2.0]
    assert transport.calls == 2


# ---------------------------------------------------------------------------
# 3. non-429 4xx never retries
# ---------------------------------------------------------------------------
def test_400_does_not_retry_real_stack() -> None:
    transport = _ScriptedTransport([_status(400, '{"error":"bad request"}')])
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    with pytest.raises(ModelDispatchError) as excinfo:
        retrying.chat(_make_request())
    assert transport.calls == 1
    assert excinfo.value.status_code == 400
    assert excinfo.value.retryable is False
    # Response body is preserved for diagnostics.
    assert "bad request" in excinfo.value.response_body


# ---------------------------------------------------------------------------
# 4. Timeouts retry via the timeout ladder
# ---------------------------------------------------------------------------
def test_timeout_retries_real_stack() -> None:
    request = httpx.Request("POST", "http://test/v1/chat/completions")
    transport = _ScriptedTransport([httpx.ReadTimeout("slow", request=request), _ok_response()])
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    response = retrying.chat(_make_request())
    assert response.id == "cmpl-1"
    assert transport.calls == 2


def test_timeout_exhausts_real_stack() -> None:
    request = httpx.Request("POST", "http://test/v1/chat/completions")
    transport = _ScriptedTransport([httpx.ReadTimeout("slow", request=request)] * 3)
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0, max_retries_timeout=1),
        sleep=lambda s: None,
    )
    with pytest.raises(ModelDispatchError) as excinfo:
        retrying.chat(_make_request())
    # 1 original + 1 retry = 2 calls.
    assert transport.calls == 2
    assert excinfo.value.retryable is True
    assert excinfo.value.status_code is None


# ---------------------------------------------------------------------------
# 5. Circuit breaker opens after repeated FINAL failures
# ---------------------------------------------------------------------------
def test_circuit_breaker_opens_after_repeated_failures_real_stack() -> None:
    # Each chat call ends in a 429 MDE after the RetryingClient exhausts.
    transport = _ScriptedTransport([_status(429)] * 12)
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0, max_retries_429=0),
        sleep=lambda s: None,
    )
    breaker = CircuitBreaker(
        inner=retrying,
        failure_threshold=3,
        window_seconds=60.0,
        cooldown_seconds=30.0,
    )
    # Three failures → breaker opens.
    for _ in range(3):
        with pytest.raises(ModelDispatchError):
            breaker.chat(_make_request())
    with pytest.raises(CircuitOpenError):
        breaker.chat(_make_request())


# ---------------------------------------------------------------------------
# 6. Error messages preserve useful detail without leaking auth header
# ---------------------------------------------------------------------------
def test_error_does_not_leak_authorization_header() -> None:
    transport = _ScriptedTransport([_status(500, '{"error":"internal"}')])
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0, max_retries_5xx=0),
        sleep=lambda s: None,
    )
    with pytest.raises(ModelDispatchError) as excinfo:
        retrying.chat(_make_request())
    # Make sure the upstream body is exposed but no header values leak.
    msg = str(excinfo.value)
    assert "internal" in excinfo.value.response_body
    assert "sk-test" not in msg
    assert "Authorization" not in msg


# ---------------------------------------------------------------------------
# 7. Success on first try still works (no regression)
# ---------------------------------------------------------------------------
def test_success_first_try_real_stack() -> None:
    transport = _ScriptedTransport([_ok_response()])
    retrying = RetryingClient(
        inner=_client(transport),
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    response = retrying.chat(_make_request())
    assert response.id == "cmpl-1"
    assert transport.calls == 1
