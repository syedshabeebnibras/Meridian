"""IngestionService — orchestrates extract → chunk → embed → store.

Every write carries ``workspace_id`` so a delete cascades correctly and
the retrieval path can WHERE-filter at the DB.

We intentionally keep this synchronous + per-document. The orchestrator's
critical path is the HTTP /v1/chat handler; ingestion happens out of band
(via /api/documents on the web side or a script) so a long-running embed
job doesn't block model traffic.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from meridian_db.models import DocumentRow
from meridian_semantic_cache.embedding import EmbeddingModel
from sqlalchemy import text

from meridian_ingestion.chunker import chunk_text
from meridian_ingestion.errors import EmptyDocumentError, IngestionError
from meridian_ingestion.extract import extract_text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("meridian.ingestion")


@dataclass(frozen=True)
class IngestionResult:
    document_id: uuid.UUID
    chunk_count: int
    byte_size: int


@dataclass
class IngestionService:
    session_factory: Callable[[], Session] | sessionmaker[Session]
    embedding_model: EmbeddingModel
    target_chunk_chars: int = 800
    overlap_chars: int = 100

    def ingest(
        self,
        *,
        workspace_id: uuid.UUID,
        uploaded_by: uuid.UUID | None,
        title: str,
        data: bytes,
        mime_type: str,
        source_uri: str | None = None,
    ) -> IngestionResult:
        # 1. Extract.
        try:
            raw_text = extract_text(data=data, mime_type=mime_type)
        except EmptyDocumentError as exc:
            raise IngestionError("document contained no extractable text") from exc

        # 2. Chunk.
        chunks = chunk_text(
            raw_text,
            target_chars=self.target_chunk_chars,
            overlap_chars=self.overlap_chars,
        )
        if not chunks:
            raise IngestionError("chunker produced 0 chunks")

        # 3. Embed (one round-trip per chunk; the embedding adapter handles
        # batching internally for the OpenAI path if it wants to).
        embeddings: list[list[float]] = [self.embedding_model.embed(c.content) for c in chunks]

        # 4. Persist atomically: a failure halfway through must NOT leave a
        # half-indexed document visible at retrieval time.
        document_id = uuid.uuid4()
        with self.session_factory.begin() as session:  # type: ignore[union-attr]
            session.add(
                DocumentRow(
                    id=document_id,
                    workspace_id=workspace_id,
                    uploaded_by=uploaded_by,
                    title=title.strip()[:512] or "Untitled",
                    source_uri=source_uri,
                    mime_type=mime_type[:128],
                    status="indexed",
                    chunk_count=len(chunks),
                    byte_size=len(data),
                )
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                session.execute(
                    text(
                        """
                        INSERT INTO document_chunks
                            (id, document_id, workspace_id, chunk_index, content,
                             content_tokens, embedding, metadata, created_at)
                        VALUES
                            (:id, :doc, :ws, :idx, :content, :tokens,
                             CAST(:embedding AS vector), CAST(:meta AS jsonb), now())
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "doc": str(document_id),
                        "ws": str(workspace_id),
                        "idx": chunk.index,
                        "content": chunk.content,
                        "tokens": _approx_tokens(chunk.content),
                        "embedding": _vec(embedding),
                        "meta": json.dumps(
                            {
                                "start_char": chunk.start_char,
                                "end_char": chunk.end_char,
                                "title": title,
                            }
                        ),
                    },
                )

        logger.info(
            "ingested document=%s workspace=%s chunks=%d bytes=%d",
            document_id,
            workspace_id,
            len(chunks),
            len(data),
        )
        return IngestionResult(
            document_id=document_id, chunk_count=len(chunks), byte_size=len(data)
        )

    def delete(self, *, workspace_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        """Delete a workspace's document + cascading chunks. Returns True on
        success, False if the document doesn't exist in this workspace."""
        with self.session_factory.begin() as session:  # type: ignore[union-attr]
            row = session.get(DocumentRow, document_id)
            if row is None or row.workspace_id != workspace_id:
                # Indistinguishable response for "doesn't exist" vs "not yours" —
                # the same anti-enumeration trick as SessionService.
                return False
            session.delete(row)
            return True


def _vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v}" for v in values) + "]"


def _approx_tokens(text_value: str) -> int:
    """Cheap token estimate — 4 chars/token rule of thumb. Good enough for
    sizing the chunk payload; the model gateway is the source of truth at
    dispatch time."""
    return max(1, len(text_value) // 4)


# Re-export for callers that import from .service directly
__all__ = ["IngestionResult", "IngestionService"]


# Silence "imported but unused" for ``datetime`` / ``UTC`` — kept available
# for future stamp ops on the row.
_ = (datetime, UTC)
