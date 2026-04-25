"""Tenant-scoped retrieval over ``document_chunks`` (pgvector).

Implements the existing ``RetrievalClient`` Protocol so the orchestrator
needs no changes. Workspace scope is read from a contextvar populated by
the API layer — this is the *only* way to query, so cross-tenant reads
are unrepresentable, not just filtered.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from meridian_contracts import RetrievalResult, RetrievedChunk
from meridian_semantic_cache.embedding import EmbeddingModel
from pydantic import HttpUrl
from sqlalchemy import text

from meridian_ingestion.context import WORKSPACE_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


@dataclass
class LocalPgvectorRetrievalClient:
    """Reads ``document_chunks`` filtered by workspace_id from the contextvar.

    The orchestrator calls ``retrieve(query, top_k=10)``. We pull the
    workspace from ``WORKSPACE_ID``; if it's unset we *return empty*
    rather than querying the whole table — getting a no-context answer is
    safer than leaking another tenant's data.
    """

    session_factory: Callable[[], Session] | sessionmaker[Session]
    embedding_model: EmbeddingModel
    placeholder_url: str = "https://docs.meridian.local"

    def retrieve(self, query: str, *, top_k: int = 10) -> RetrievalResult:
        started = time.perf_counter()
        workspace = WORKSPACE_ID.get()
        if workspace is None:
            # Fail closed: no workspace, no docs. The orchestrator's refusal
            # path then handles "no relevant docs".
            return _empty(query, started)

        try:
            workspace_uuid = uuid.UUID(workspace)
        except ValueError:
            return _empty(query, started)

        embedding = self.embedding_model.embed(query)

        with self.session_factory() as session:
            rows = session.execute(
                text(
                    """
                    SELECT c.id::text                                     AS chunk_id,
                           c.content                                       AS content,
                           c.metadata                                      AS metadata,
                           d.title                                         AS title,
                           d.source_uri                                    AS source_uri,
                           1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.workspace_id = :ws
                    ORDER BY c.embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                    """
                ),
                {
                    "embedding": _vec(embedding),
                    "ws": str(workspace_uuid),
                    "top_k": top_k,
                },
            ).all()

        chunks: list[RetrievedChunk] = []
        for i, row in enumerate(rows, start=1):
            similarity = max(0.0, min(1.0, float(row.similarity)))
            chunks.append(
                RetrievedChunk(
                    index=i,
                    chunk_id=row.chunk_id,
                    source_title=row.title or "Untitled",
                    source_url=HttpUrl(row.source_uri or self.placeholder_url),
                    content=row.content,
                    relevance_score=similarity,
                    metadata={k: str(v) for k, v in (row.metadata or {}).items()},
                )
            )

        elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
        return RetrievalResult(
            query=query,
            query_rewritten=query,
            results=chunks,
            total_chunks_retrieved=len(chunks),
            total_after_rerank=len(chunks),
            retrieval_latency_ms=elapsed_ms,
        )


def _empty(query: str, started: float) -> RetrievalResult:
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    return RetrievalResult(
        query=query,
        query_rewritten=query,
        results=[],
        total_chunks_retrieved=0,
        total_after_rerank=0,
        retrieval_latency_ms=elapsed_ms,
    )


def _vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v}" for v in values) + "]"
