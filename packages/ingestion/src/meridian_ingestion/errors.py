"""Ingestion error taxonomy."""

from __future__ import annotations


class IngestionError(RuntimeError):
    """Base class for ingestion failures."""


class UnknownMimeTypeError(IngestionError):
    """Raised when we can't extract text from the supplied bytes/MIME."""


class EmptyDocumentError(IngestionError):
    """Raised when extraction yields no usable text — refuse to index empty docs
    so the chunk count never lies about coverage."""
