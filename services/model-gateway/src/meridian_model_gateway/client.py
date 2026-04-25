"""LiteLLM client — thin, synchronous, OpenAI-compatible.

LiteLLM exposes OpenAI's `POST /v1/chat/completions` shape, so we speak that
directly.

Error contract
--------------
Every failure surfaces as ``ModelDispatchError``. The error carries typed
fields (``status_code``, ``retryable``, ``response_body``) so the retry
layer can decide whether to replay the request without re-parsing httpx
internals. Direct callers (regression runs, bootstrap) can ignore those
fields and still rely on a single exception type.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from meridian_contracts import ModelRequest, ModelResponse, ModelUsage


class ModelDispatchError(RuntimeError):
    """Any failure reaching or parsing the gateway.

    Attributes
    ----------
    status_code:
        Upstream HTTP status when available; ``None`` for transport errors
        (timeout, DNS, connection reset).
    retryable:
        Whether the retry layer should replay this request. Set by the
        constructor based on the status code / cause — 429, 5xx, and
        transport errors are retryable; 4xx (non-429) are not.
    response_body:
        First 500 bytes of the upstream response body for diagnostics.
        Never log full body — may contain PII.
    cause_type:
        String name of the underlying exception class for logs/metrics.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
        response_body: str = "",
        cause_type: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.cause_type = cause_type
        self.retryable = retryable if retryable is not None else self._infer_retryable(status_code)

    @staticmethod
    def _infer_retryable(status_code: int | None) -> bool:
        if status_code is None:
            # Transport-level failure — timeout / connect error / DNS.
            return True
        if status_code == 429:
            return True
        return 500 <= status_code < 600


@dataclass(frozen=True)
class LiteLLMConfig:
    base_url: str = "http://localhost:4000"
    api_key: str = ""
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> LiteLLMConfig:
        return cls(
            base_url=os.environ.get("LITELLM_BASE_URL", "http://localhost:4000"),
            api_key=os.environ.get("LITELLM_MASTER_KEY", ""),
            timeout_s=float(os.environ.get("LITELLM_TIMEOUT_S", "60.0")),
        )


class LiteLLMClient:
    """Synchronous client over /v1/chat/completions.

    Meant for offline flows (regression runs, bootstraps). The orchestrator's
    production path wraps this in ``RetryingClient`` + ``CircuitBreaker``.
    """

    def __init__(
        self,
        config: LiteLLMConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config or LiteLLMConfig.from_env()
        self._http = httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout_s,
            headers={"Authorization": f"Bearer {self._config.api_key}"}
            if self._config.api_key
            else {},
            transport=transport,  # tests inject httpx.MockTransport here
        )

    def chat(self, request: ModelRequest) -> ModelResponse:
        body = _build_body(request)
        started = time.perf_counter()
        try:
            response = self._http.post("/v1/chat/completions", json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Preserve status code + truncated body so the retry layer can
            # decide whether this is a 429/5xx (retry) or 4xx (don't).
            raise ModelDispatchError(
                f"LiteLLM call failed: {exc.response.status_code}",
                status_code=exc.response.status_code,
                response_body=_truncate(exc.response.text if exc.response is not None else ""),
                cause_type=type(exc).__name__,
            ) from exc
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            # Transport-level — retryable with no HTTP status.
            raise ModelDispatchError(
                f"LiteLLM call failed ({type(exc).__name__}): {exc}",
                status_code=None,
                retryable=True,
                cause_type=type(exc).__name__,
            ) from exc
        except httpx.HTTPError as exc:
            # Anything else httpx throws — be conservative, don't retry.
            raise ModelDispatchError(
                f"LiteLLM call failed: {exc}",
                status_code=None,
                retryable=False,
                cause_type=type(exc).__name__,
            ) from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        return _parse_response(data, elapsed_ms)

    def close(self) -> None:
        self._http.close()


def _truncate(text: str, limit: int = 500) -> str:
    """Clip response bodies so they don't blow up log lines / tracebacks."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _build_body(request: ModelRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [m.model_dump() for m in request.messages],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    if request.response_format is not None:
        body["response_format"] = request.response_format.model_dump(
            by_alias=True, exclude_none=True
        )
    if request.metadata:
        body["metadata"] = dict(request.metadata)
    return body


def _parse_response(data: dict[str, Any], latency_ms: int) -> ModelResponse:
    """Convert OpenAI-shaped JSON into ModelResponse.

    LiteLLM sometimes returns structured content as a JSON string; we keep it
    as-is if parsing fails so callers can diagnose.
    """
    choices = data.get("choices") or []
    if not choices:
        raise ModelDispatchError(
            f"LiteLLM response had no choices: {_truncate(str(data))}",
            status_code=None,
            retryable=False,
            cause_type="InvalidResponse",
        )
    message = choices[0]["message"]
    content = message.get("content", "")

    # If structured output was requested the content is a JSON string; try to parse.
    parsed: dict[str, Any] | str = content
    if isinstance(content, str) and content.strip().startswith("{"):
        import json as _json

        try:
            parsed = _json.loads(content)
        except _json.JSONDecodeError:
            parsed = content

    usage = data.get("usage") or {}
    return ModelResponse(
        id=str(data.get("id", "unknown")),
        model=str(data.get("model", "unknown")),
        content=parsed,
        usage=ModelUsage(
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0)),
            cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0)),
        ),
        latency_ms=latency_ms,
    )
