"""HttpRetrievalClient + ThresholdingClient tests using httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from meridian_contracts import RetrievalResult
from meridian_retrieval_client import (
    HttpRetrievalClient,
    RetrievalConfig,
    ThresholdingClient,
)
from meridian_retrieval_client.http import RetrievalDispatchError


def _payload(scores: list[float]) -> dict[str, Any]:
    return {
        "query": "q",
        "query_rewritten": "q",
        "results": [
            {
                "index": i + 1,
                "chunk_id": f"c{i}",
                "source_title": f"t{i}",
                "source_url": "https://example.com/",
                "content": "c",
                "relevance_score": s,
            }
            for i, s in enumerate(scores)
        ],
        "total_chunks_retrieved": len(scores),
        "total_after_rerank": len(scores),
        "retrieval_latency_ms": 42,
    }


def test_http_client_parses_section_8_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/retrieve"
        body = json.loads(request.content)
        assert body == {"query": "test", "top_k": 3}
        return httpx.Response(200, json=_payload([0.9, 0.7, 0.5]))

    http = httpx.Client(base_url="http://rag", transport=httpx.MockTransport(handler))
    client = HttpRetrievalClient(RetrievalConfig(base_url="http://rag"), http=http)
    result = client.retrieve("test", top_k=3)

    assert isinstance(result, RetrievalResult)
    assert [c.relevance_score for c in result.results] == [0.9, 0.7, 0.5]
    assert result.retrieval_latency_ms == 42


def test_http_client_wraps_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    http = httpx.Client(base_url="http://rag", transport=httpx.MockTransport(handler))
    client = HttpRetrievalClient(RetrievalConfig(base_url="http://rag"), http=http)
    with pytest.raises(RetrievalDispatchError):
        client.retrieve("q")


def test_http_client_sends_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=_payload([0.9]))

    http = httpx.Client(
        base_url="http://rag",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer secret-key"},
    )
    client = HttpRetrievalClient(RetrievalConfig(base_url="http://rag"), http=http)
    client.retrieve("q")
    assert seen["auth"] == "Bearer secret-key"


def test_thresholding_drops_low_relevance_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload([0.9, 0.6, 0.3, 0.1]))

    http = httpx.Client(base_url="http://rag", transport=httpx.MockTransport(handler))
    inner = HttpRetrievalClient(RetrievalConfig(base_url="http://rag"), http=http)
    client = ThresholdingClient(inner=inner, min_relevance=0.5)
    result = client.retrieve("q")
    assert [c.relevance_score for c in result.results] == [0.9, 0.6]
    assert result.total_after_rerank == 2


def test_thresholding_empty_signals_no_retrieval() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload([0.2, 0.1]))

    http = httpx.Client(base_url="http://rag", transport=httpx.MockTransport(handler))
    inner = HttpRetrievalClient(RetrievalConfig(base_url="http://rag"), http=http)
    client = ThresholdingClient(inner=inner, min_relevance=0.5)
    result = client.retrieve("q")
    assert result.results == []
    assert result.total_after_rerank == 0
