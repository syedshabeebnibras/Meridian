"""Plain-text → chunks.

Sliding-window chunker over paragraph boundaries. Defaults are tuned for
prose (~800 chars / 100 char overlap) so each chunk fits comfortably under
a model's per-chunk attention budget while preserving enough overlap that
sentence-spanning context isn't lost at the boundary.

The chunker is intentionally byte-agnostic: it counts characters, not
tokens, because we don't want a per-package tokeniser dep. The orchestrator
already counts tokens at assembly time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    index: int  # 0-based position in the document
    content: str  # the chunk text
    start_char: int  # inclusive offset in the source document
    end_char: int  # exclusive offset


# Paragraph break = two-or-more newlines. Single newlines are preserved
# inside a chunk so list items + line-broken markdown stay readable.
_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")


def chunk_text(
    text: str,
    *,
    target_chars: int = 800,
    overlap_chars: int = 100,
) -> list[Chunk]:
    """Greedy sliding window over paragraph-joined text.

    The chunk emits whenever the running buffer exceeds ``target_chars``;
    we then carry the trailing ``overlap_chars`` into the next chunk so a
    sentence that straddles the boundary is searchable from either side.

    Empty / whitespace-only output is filtered, so a 100-paragraph document
    of blank lines yields zero chunks rather than crashing downstream.
    """
    if target_chars <= 0:
        raise ValueError("target_chars must be > 0")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("overlap_chars must be in [0, target_chars)")

    paragraphs = [p for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    cursor = 0  # absolute char offset into ``text``
    buffer = ""
    buffer_start = 0

    for para in paragraphs:
        # Locate this paragraph in the original text so end_char stays accurate
        # even when the paragraph appears multiple times.
        para_start = text.find(para, cursor)
        if para_start == -1:
            para_start = cursor
        para_end = para_start + len(para)
        cursor = para_end

        if not buffer:
            buffer_start = para_start
        # Join with a paragraph break so chunks read like the source.
        buffer = (buffer + "\n\n" + para) if buffer else para

        while len(buffer) >= target_chars:
            cut = _safe_cut(buffer, target_chars)
            chunk_content = buffer[:cut].strip()
            if chunk_content:
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        content=chunk_content,
                        start_char=buffer_start,
                        end_char=buffer_start + cut,
                    )
                )
            # Slide the window forward; keep ``overlap_chars`` for context.
            slide = max(1, cut - overlap_chars)
            buffer = buffer[slide:]
            buffer_start += slide

    if buffer.strip():
        chunks.append(
            Chunk(
                index=len(chunks),
                content=buffer.strip(),
                start_char=buffer_start,
                end_char=buffer_start + len(buffer),
            )
        )
    return chunks


def _safe_cut(text: str, target: int) -> int:
    """Pick the cut point at ``target`` but back up to a sentence-ish break
    if one is nearby — keeps chunks from ending mid-word."""
    if target >= len(text):
        return len(text)
    # Look back up to 80 chars for ``. ``, ``? ``, ``! `` or ``\n`` — each
    # is a reasonable sentence-ish boundary in English / markdown.
    window = text[max(0, target - 80) : target]
    for marker in (". ", "? ", "! ", "\n"):
        idx = window.rfind(marker)
        if idx >= 0:
            return target - 80 + idx + len(marker)
    # Fall back to nearest space, then to the hard target.
    space_idx = text.rfind(" ", max(0, target - 40), target)
    return space_idx + 1 if space_idx > 0 else target
