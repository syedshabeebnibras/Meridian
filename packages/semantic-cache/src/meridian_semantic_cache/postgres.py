"""Postgres + pgvector backed SemanticCache.

Requires migration 0004 to have run. Schema:

  CREATE TABLE semantic_cache (
    id uuid PRIMARY KEY,
    partition_key text NOT NULL,
    query text NOT NULL,
    embedding vector(<dim>) NOT NULL,
    content jsonb NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}',
    stored_at timestamptz NOT NULL DEFAULT now()
  );
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from meridian_semantic_cache.cache import CacheHit, CacheLookupResult, CacheMiss
from meridian_semantic_cache.embedding import EmbeddingModel
from meridian_semantic_cache.memory import _hash_partition

SessionFactory = Callable[[], Session]


@dataclass
class PostgresSemanticCache:
    embedding_model: EmbeddingModel
    session_factory: SessionFactory
    ttl_seconds: float = 3600.0

    def lookup(
        self, *, query: str, partition_key: str, min_similarity: float = 0.95
    ) -> CacheLookupResult:
        embedding = self.embedding_model.embed(query)
        partition = _hash_partition(partition_key)
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=self.ttl_seconds)

        with self.session_factory() as session:
            # Order by cosine distance (ascending) so the first row is the best match.
            row = session.execute(
                text(
                    """
                    SELECT query, content, stored_at, metadata,
                           1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM semantic_cache
                    WHERE partition_key = :partition
                      AND stored_at >= :cutoff
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 1
                    """
                ),
                {
                    "embedding": _to_pg_vector(embedding),
                    "partition": partition,
                    "cutoff": cutoff,
                },
            ).first()

        if row is None:
            return CacheMiss(reason="no entries in partition")
        similarity = float(row[4])
        if similarity >= min_similarity:
            return CacheHit(
                response_content=_content_from_db(row[1]),
                original_query=row[0],
                similarity=similarity,
                stored_at=row[2],
                metadata=dict(row[3] or {}),
            )
        return CacheMiss(reason="below similarity threshold", closest_similarity=similarity)

    def store(
        self,
        *,
        query: str,
        partition_key: str,
        response_content: dict[str, Any] | str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        embedding = self.embedding_model.embed(query)
        partition = _hash_partition(partition_key)
        payload = (
            response_content if isinstance(response_content, dict) else {"_text": response_content}
        )

        with self.session_factory() as session:
            session.execute(
                text(
                    """
                    INSERT INTO semantic_cache
                        (id, partition_key, query, embedding, content, metadata, stored_at)
                    VALUES
                        (:id, :partition, :query, CAST(:embedding AS vector),
                         CAST(:content AS jsonb), CAST(:metadata AS jsonb), now())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "partition": partition,
                    "query": query,
                    "embedding": _to_pg_vector(embedding),
                    "content": json.dumps(payload),
                    "metadata": json.dumps(metadata or {}),
                },
            )
            session.commit()


def _to_pg_vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v}" for v in values) + "]"


def _content_from_db(value: Any) -> dict[str, Any] | str:
    if isinstance(value, dict):
        if set(value.keys()) == {"_text"}:
            return str(value["_text"])
        return value
    return str(value)
