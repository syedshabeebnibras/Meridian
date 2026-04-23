"""SemanticCache Protocol + shared result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class CacheHit:
    response_content: dict[str, Any] | str
    original_query: str
    similarity: float
    stored_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class CacheMiss:
    reason: str
    closest_similarity: float = 0.0


CacheLookupResult = CacheHit | CacheMiss


class SemanticCache(Protocol):
    """Anything that can look up + store semantic cache entries."""

    def lookup(
        self, *, query: str, partition_key: str, min_similarity: float = 0.95
    ) -> CacheLookupResult: ...

    def store(
        self,
        *,
        query: str,
        partition_key: str,
        response_content: dict[str, Any] | str,
        metadata: dict[str, str] | None = None,
    ) -> None: ...
