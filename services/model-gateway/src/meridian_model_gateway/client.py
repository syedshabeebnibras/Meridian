"""LiteLLM client — thin, synchronous, OpenAI-compatible.

LiteLLM exposes OpenAI's `POST /v1/chat/completions` shape, so we speak that
directly. Retry / failover / instrumentation come in Phase 3.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from meridian_contracts import ModelRequest, ModelResponse, ModelUsage


class ModelDispatchError(RuntimeError):
    """Wraps any failure calling the gateway so callers have one exception type."""


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
    Phase 3 path uses an async wrapper on top of this.
    """

    def __init__(self, config: LiteLLMConfig | None = None) -> None:
        self._config = config or LiteLLMConfig.from_env()
        self._http = httpx.Client(
            base_url=self._config.base_url,
            timeout=self._config.timeout_s,
            headers={"Authorization": f"Bearer {self._config.api_key}"}
            if self._config.api_key
            else {},
        )

    def chat(self, request: ModelRequest) -> ModelResponse:
        body = _build_body(request)
        started = time.perf_counter()
        try:
            response = self._http.post("/v1/chat/completions", json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Include the upstream error body so the cause is visible in logs.
            detail = exc.response.text[:500] if exc.response is not None else ""
            raise ModelDispatchError(
                f"LiteLLM call failed: {exc.response.status_code} {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelDispatchError(f"LiteLLM call failed: {exc}") from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        return _parse_response(data, elapsed_ms)

    def close(self) -> None:
        self._http.close()


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
        raise ModelDispatchError(f"LiteLLM response had no choices: {data}")
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
