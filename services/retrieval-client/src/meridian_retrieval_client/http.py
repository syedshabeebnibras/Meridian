"""HttpRetrievalClient — thin wrapper over the Data Platform team's RAG API.

Contract (aligned with Section 8 RetrievalResult):

  POST {base_url}/retrieve
  { "query": "...", "top_k": <int> }

Response body is parsed with Pydantic's RetrievalResult — any schema drift
surfaces as a ValidationError immediately rather than silently propagating.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from meridian_contracts import RetrievalResult


class RetrievalDispatchError(RuntimeError):
    """Wraps any failure calling the RAG gateway so callers have one exception type."""


@dataclass(frozen=True)
class RetrievalConfig:
    base_url: str = "http://localhost:5100"
    api_key: str = ""
    timeout_s: float = 2.0  # Section 7 §Timeouts — retrieval budget

    @classmethod
    def from_env(cls) -> RetrievalConfig:
        return cls(
            base_url=os.environ.get("RAG_BASE_URL", "http://localhost:5100"),
            api_key=os.environ.get("RAG_API_KEY", ""),
            timeout_s=float(os.environ.get("RAG_TIMEOUT_S", "2.0")),
        )


class HttpRetrievalClient:
    """Synchronous RAG client. Accepts an optional custom httpx.Client so tests
    can inject a MockTransport without hitting the network."""

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        *,
        http: httpx.Client | None = None,
    ) -> None:
        self._config = config or RetrievalConfig.from_env()
        if http is not None:
            self._http = http
        else:
            headers: dict[str, str] = {}
            if self._config.api_key:
                headers["Authorization"] = f"Bearer {self._config.api_key}"
            self._http = httpx.Client(
                base_url=self._config.base_url,
                timeout=self._config.timeout_s,
                headers=headers,
            )

    def retrieve(self, query: str, *, top_k: int = 10) -> RetrievalResult:
        try:
            response = self._http.post(
                "/retrieve",
                json={"query": query, "top_k": top_k},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RetrievalDispatchError(f"RAG call failed: {exc}") from exc
        return RetrievalResult.model_validate(response.json())

    def close(self) -> None:
        self._http.close()
