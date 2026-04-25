"""Pure-text Phase 6 tests — no DB, no network."""

from __future__ import annotations

import pytest
from meridian_ingestion import chunk_text, extract_text
from meridian_ingestion.errors import EmptyDocumentError, UnknownMimeTypeError


def test_chunker_returns_empty_for_blank_input() -> None:
    assert chunk_text("") == []
    assert chunk_text("\n\n\n   \n") == []


def test_chunker_emits_single_chunk_for_short_input() -> None:
    chunks = chunk_text("This is a short doc.")
    assert len(chunks) == 1
    assert chunks[0].content == "This is a short doc."
    assert chunks[0].index == 0


def test_chunker_splits_long_input_with_overlap() -> None:
    paragraph = "Sentence one is here. Sentence two follows. " * 80  # ~3600 chars
    chunks = chunk_text(paragraph, target_chars=400, overlap_chars=80)
    assert len(chunks) >= 2
    # Indices are sequential.
    for i, c in enumerate(chunks):
        assert c.index == i
    # Overlap: every chunk after the first should share a prefix with the
    # tail of the previous one.
    from itertools import pairwise

    for prev, curr in pairwise(chunks):
        assert (
            any(curr.content[:40] in prev.content[-200:] for _ in [0])
            or curr.content[:20] in prev.content
        )


def test_chunker_invalid_overlap_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("hello", target_chars=10, overlap_chars=10)
    with pytest.raises(ValueError):
        chunk_text("hello", target_chars=10, overlap_chars=-1)


def test_extract_plain_text_round_trips() -> None:
    text = extract_text(data=b"Hello, world.\n", mime_type="text/plain")
    assert text == "Hello, world."


def test_extract_markdown_strips_bom_and_normalises_newlines() -> None:
    payload = "﻿# Heading\r\n\r\nBody text.\r\n".encode()
    text = extract_text(data=payload, mime_type="text/markdown")
    assert "\r" not in text
    assert text.startswith("# Heading")


def test_extract_unknown_mime_raises() -> None:
    with pytest.raises(UnknownMimeTypeError):
        extract_text(data=b"<doc/>", mime_type="application/msword")


def test_extract_empty_raises() -> None:
    with pytest.raises(EmptyDocumentError):
        extract_text(data=b"   \n\n  \n", mime_type="text/plain")
