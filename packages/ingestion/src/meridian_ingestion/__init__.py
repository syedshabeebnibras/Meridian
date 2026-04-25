"""Local document ingestion + tenant-scoped retrieval (Phase 6).

Public surface:

  - ``extract_text`` / ``extract_pdf`` — file → plain text
  - ``chunk_text``                     — plain text → list[Chunk]
  - ``IngestionService``               — orchestrates extract → chunk → embed → store
  - ``LocalPgvectorRetrievalClient``   — tenant-scoped retrieval over pgvector
  - ``WORKSPACE_ID``                   — contextvar threading workspace through
                                         the request without changing the
                                         RetrievalClient Protocol
  - ``IngestionError``, ``UnknownMimeTypeError``

Tenant isolation is enforced in two places:
  1. Every write carries ``workspace_id`` — schema FKs cascade on workspace
     delete, so tearing down a tenant cleans up its corpus.
  2. The retrieval client refuses to query without a workspace_id in the
     contextvar; cross-tenant reads are *unrepresentable* by the API surface,
     not just filtered.
"""

from meridian_ingestion.chunker import Chunk, chunk_text
from meridian_ingestion.context import WORKSPACE_ID
from meridian_ingestion.errors import IngestionError, UnknownMimeTypeError
from meridian_ingestion.extract import extract_pdf, extract_text
from meridian_ingestion.retrieval import LocalPgvectorRetrievalClient
from meridian_ingestion.service import IngestionResult, IngestionService

__all__ = [
    "WORKSPACE_ID",
    "Chunk",
    "IngestionError",
    "IngestionResult",
    "IngestionService",
    "LocalPgvectorRetrievalClient",
    "UnknownMimeTypeError",
    "chunk_text",
    "extract_pdf",
    "extract_text",
]
