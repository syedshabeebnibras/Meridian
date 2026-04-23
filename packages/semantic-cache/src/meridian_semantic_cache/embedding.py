"""Embedding Protocol + deterministic in-process model for tests.

Phase 9 wires the real OpenAI / Voyage / Cohere embedding call. The
StaticEmbedding here uses sha256 → unit vector for deterministic tests
that don't need semantic meaning.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


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
