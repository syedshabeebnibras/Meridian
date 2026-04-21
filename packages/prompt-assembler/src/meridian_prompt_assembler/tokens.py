"""Token counting — tiktoken cl100k_base for now.

cl100k_base is OpenAI's GPT-4 encoder. It is not Claude's native tokenizer,
so counts are approximations for Anthropic models (typically within ~10%).
Phase 6 can swap in provider-specific counters behind this Protocol without
touching the assembler.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import tiktoken


class TokenCounterProtocol(Protocol):
    def count(self, text: str) -> int: ...


@lru_cache(maxsize=4)
def _encoder(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


class TokenCounter:
    """Default token counter — cl100k_base, good enough for Phase 2 budgeting."""

    def __init__(self, encoding: str = "cl100k_base") -> None:
        self._encoding_name = encoding

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(_encoder(self._encoding_name).encode(text))
