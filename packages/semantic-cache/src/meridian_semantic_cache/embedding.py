"""Embedding Protocol + deterministic in-process model for tests.

Production uses OpenAIEmbedding (text-embedding-3-small by default). The
StaticEmbedding uses sha256 → unit vector for deterministic tests that
don't need semantic meaning.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class EmbeddingModel(Protocol):
    dimension: int

    def embed(self, text: str) -> list[float]: ...


@dataclass
class StaticEmbedding:
    """Deterministic hash-based embedding for tests. NOT semantically useful —
    identical text returns identical vectors, different text returns different
    vectors. That's all the cache needs to exercise exact + near-miss paths.
    """

    dimension: int = 128

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Produce `dimension` floats in [-1, 1] from the digest.
        values: list[float] = []
        while len(values) < self.dimension:
            for b in digest:
                values.append((b / 127.5) - 1.0)
                if len(values) >= self.dimension:
                    break
        # Normalize to unit vector.
        norm = sum(v * v for v in values) ** 0.5
        if norm == 0:
            return values
        return [v / norm for v in values]


@dataclass
class OpenAIEmbedding:
    """Real OpenAI embeddings via the /v1/embeddings HTTP endpoint.

    We hit the HTTP API directly instead of the `openai` SDK so the
    package doesn't pull in a heavy transitive dep (and so the same
    adapter works whether LiteLLM is in front of us or not).
    """

    model: str = "text-embedding-3-small"
    dimension: int = 1536  # default for text-embedding-3-small
    api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    timeout_s: float = 10.0

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set; cannot call OpenAI embeddings API"
            )
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": text},
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
        return list(payload["data"][0]["embedding"])
