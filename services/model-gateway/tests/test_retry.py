"""Retry layer tests — exercise each row of the Section 7 policy table."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from meridian_contracts import ModelRequest, ModelResponse, ModelUsage
from meridian_model_gateway import ModelDispatchError, RetryingClient, RetryPolicy


class _Recorder:
    """Fake inner client — plays back a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[Callable[[ModelRequest], ModelResponse]]) -> None:
        self._outcomes = outcomes
        self.calls: list[ModelRequest] = []

    def chat(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        outcome = self._outcomes.pop(0)
        return outcome(request)


def _good_response(request: ModelRequest) -> ModelResponse:
    return ModelResponse(
        id="ok",
        model=request.model,
        content={"ok": True},
        usage=ModelUsage(input_tokens=0, output_tokens=0),
        latency_ms=10,
    )


def _raise_status(code: int) -> Callable[[ModelRequest], ModelResponse]:
    def _fn(_: ModelRequest) -> ModelResponse:
        response = httpx.Response(code, content=b'{"error":"x"}')
        request = httpx.Request("POST", "http://test/v1/chat/completions")
        raise httpx.HTTPStatusError("boom", request=request, response=response)

    return _fn


def _raise_timeout(_: ModelRequest) -> ModelResponse:
    raise httpx.ReadTimeout("slow")


def _make_request() -> ModelRequest:
    return ModelRequest(
        model="meridian-mid",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=128,
    )


def _sleep_tracker() -> tuple[Callable[[float], None], list[float]]:
    calls: list[float] = []
    return calls.append, calls


def test_429_retries_up_to_policy() -> None:
    inner = _Recorder([_raise_status(429), _raise_status(429), _good_response])
    sleep_calls, sleeps = _sleep_tracker()
    client = RetryingClient(
        inner=inner,  # type: ignore[arg-type]
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=sleep_calls,
    )
    response = client.chat(_make_request())
    assert response.content == {"ok": True}
    assert len(inner.calls) == 3
    assert sleeps == [1.0, 3.0]  # attempts 1,2 sleep before retry; attempt 3 succeeds
    assert inner.calls[-1].metadata["attempt"] == "3"


def test_429_exhausts_after_max_retries() -> None:
    inner = _Recorder([_raise_status(429)] * 4)
    client = RetryingClient(
        inner=inner,  # type: ignore[arg-type]
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    with pytest.raises(ModelDispatchError):
        client.chat(_make_request())
    # max_retries_429 = 3 ⇒ 1 original + 3 retries = 4 attempts.
    assert len(inner.calls) == 4


def test_5xx_retries_per_policy() -> None:
    inner = _Recorder([_raise_status(503), _good_response])
    sleep_calls, sleeps = _sleep_tracker()
    client = RetryingClient(
        inner=inner,  # type: ignore[arg-type]
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=sleep_calls,
    )
    response = client.chat(_make_request())
    assert response.content == {"ok": True}
    assert len(inner.calls) == 2
    assert sleeps == [2.0]


def test_4xx_non_429_does_not_retry() -> None:
    inner = _Recorder([_raise_status(400)])
    client = RetryingClient(
        inner=inner,  # type: ignore[arg-type]
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    with pytest.raises(ModelDispatchError):
        client.chat(_make_request())
    assert len(inner.calls) == 1


def test_timeout_retries_once() -> None:
    inner = _Recorder([_raise_timeout, _good_response])
    client = RetryingClient(
        inner=inner,  # type: ignore[arg-type]
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    response = client.chat(_make_request())
    assert response.content == {"ok": True}
    assert len(inner.calls) == 2


def test_attempt_metadata_increments() -> None:
    inner = _Recorder([_raise_status(429), _good_response])
    client = RetryingClient(
        inner=inner,  # type: ignore[arg-type]
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda s: None,
    )
    client.chat(_make_request())
    assert [c.metadata["attempt"] for c in inner.calls] == ["1", "2"]
