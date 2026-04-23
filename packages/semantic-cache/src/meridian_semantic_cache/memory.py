"""In-memory SemanticCache — tests + single-process dev."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from meridian_semantic_cache.cache import CacheHit, CacheLookupResult, CacheMiss
from meridian_semantic_cache.embedding import EmbeddingModel


def _hash_partition(partition_key: str) -> str:
    return hashlib.sha256(partition_key.encode("utf-8")).hexdigest()[:16]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot: float = sum(x * y for x, y in zip(a, b, strict=True))
    na: float = sum(x * x for x in a) ** 0.5
    nb: float = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


@dataclass
class _Entry:
    query: str
    partition: str
    embedding: list[float]
    content: dict[str, Any] | str
    stored_at: datetime
    metadata: dict[str, str]


@dataclass
class InMemorySemanticCache:
    embedding_model: EmbeddingModel
    ttl_seconds: float = 3600.0
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))
    _entries: list[_Entry] = field(default_factory=list)

    def _evict_stale(self) -> None:
        cutoff = self.clock() - timedelta(seconds=self.ttl_seconds)
        self._entries = [e for e in self._entries if e.stored_at >= cutoff]

    def lookup(
        self, *, query: str, partition_key: str, min_similarity: float = 0.95
    ) -> CacheLookupResult:
        self._evict_stale()
        partition = _hash_partition(partition_key)
        relevant = [e for e in self._entries if e.partition == partition]
        if not relevant:
            return CacheMiss(reason="no entries in partition")
        query_embedding = self.embedding_model.embed(query)
        best: tuple[float, _Entry] | None = None
        for entry in relevant:
            sim = _cosine(query_embedding, entry.embedding)
            if best is None or sim > best[0]:
                best = (sim, entry)
        assert best is not None
        sim, entry = best
        if sim >= min_similarity:
            return CacheHit(
                response_content=entry.content,
                original_query=entry.query,
                similarity=sim,
                stored_at=entry.stored_at,
                metadata=dict(entry.metadata),
            )
        return CacheMiss(reason="below similarity threshold", closest_similarity=sim)

    def store(
        self,
        *,
        query: str,
        partition_key: str,
        response_content: dict[str, Any] | str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self._evict_stale()
        self._entries.append(
            _Entry(
                query=query,
                partition=_hash_partition(partition_key),
                embedding=self.embedding_model.embed(query),
                content=response_content,
                stored_at=self.clock(),
                metadata=dict(metadata or {}),
            )
        )
