"""Source-file → plain text extraction.

We support three input shapes:

  - ``text/plain`` and ``text/markdown``  — round-trip the bytes through
    UTF-8 (with replacement for stray bytes), strip BOM, normalise line
    endings.
  - ``application/pdf``                   — extract per-page text via
    ``pypdf``. We deliberately do not OCR; documents that are *images*
    of text need a different pipeline.

Extraction never raises on weird-but-decodeable input — that's the
chunker's job to discard. We do raise ``UnknownMimeTypeError`` for
formats we can't read at all (Word, Excel, etc.), since indexing such
a file silently would give the user the false impression their docs
are searchable.
"""

from __future__ import annotations

import io

from meridian_ingestion.errors import EmptyDocumentError, UnknownMimeTypeError


def extract_text(*, data: bytes, mime_type: str) -> str:
    """Dispatch on MIME type; return plain text. Empty result → raise."""
    mime = (mime_type or "").lower().split(";", 1)[0].strip()
    if mime in ("text/plain", "text/markdown", "text/x-markdown", ""):
        text = _decode_text(data)
    elif mime == "application/pdf":
        text = extract_pdf(data)
    else:
        raise UnknownMimeTypeError(f"unsupported MIME type: {mime!r}")

    text = text.strip()
    if not text:
        raise EmptyDocumentError("extracted document has no text")
    return text


def extract_pdf(data: bytes) -> str:
    """Per-page extraction via pypdf. Pages joined with double newlines so
    the chunker treats them as paragraph breaks."""
    # Local import keeps pypdf optional for environments that only need
    # plain-text ingestion (e.g. dev fixtures).
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            # Skip a corrupt page rather than failing the whole upload —
            # users would rather index 99% of a long PDF than retry.
            pages.append("")
    return "\n\n".join(p for p in pages if p)


def _decode_text(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    return text.replace("\r\n", "\n").replace("\r", "\n")
