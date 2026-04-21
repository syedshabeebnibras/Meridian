"""Protocol every retrieval implementation must satisfy.

Phase 3: MockRetrievalClient (in-process fixtures).
Phase 4: real RAG client over HTTP (Section 8 RetrievalResult contract).
"""

from __future__ import annotations

from typing import Protocol

from meridian_contracts import RetrievalResult


class RetrievalClient(Protocol):
    def retrieve(self, query: str, *, top_k: int = 10) -> RetrievalResult: ...
