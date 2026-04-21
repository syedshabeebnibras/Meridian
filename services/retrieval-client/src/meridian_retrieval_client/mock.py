"""MockRetrievalClient — fixture-backed retrieval for tests + dev.

Fixtures live in a YAML keyed by a query substring. The first key whose
value appears in the query (case-insensitive) wins. An empty-key entry
acts as the fallback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from meridian_contracts import RetrievalResult, RetrievedChunk
from pydantic import HttpUrl


@dataclass(frozen=True)
class FixtureEntry:
    match: str  # substring to look for in the query (case-insensitive)
    chunks: list[RetrievedChunk]


@dataclass
class MockRetrievalClient:
    fixtures: list[FixtureEntry] = field(default_factory=list)
    default_latency_ms: int = 10

    def retrieve(self, query: str, *, top_k: int = 10) -> RetrievalResult:
        started = time.perf_counter()
        lowered = query.lower()
        matched: list[RetrievedChunk] = []
        for entry in self.fixtures:
            if entry.match == "" or entry.match.lower() in lowered:
                matched = list(entry.chunks[:top_k])
                break
        elapsed_ms = max(self.default_latency_ms, int((time.perf_counter() - started) * 1000))
        return RetrievalResult(
            query=query,
            query_rewritten=query,
            results=matched,
            total_chunks_retrieved=len(matched),
            total_after_rerank=len(matched),
            retrieval_latency_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------
    @classmethod
    def from_yaml(cls, path: Path) -> MockRetrievalClient:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or "fixtures" not in raw:
            raise ValueError(f"{path}: expected a mapping with top-level 'fixtures'")

        entries: list[FixtureEntry] = []
        for item in raw["fixtures"]:
            chunks: list[RetrievedChunk] = []
            for i, doc in enumerate(item.get("chunks", []), start=1):
                chunks.append(
                    RetrievedChunk(
                        index=i,
                        chunk_id=doc.get("chunk_id", f"mock_{i}"),
                        source_title=doc["source_title"],
                        source_url=HttpUrl(doc["source_url"]),
                        content=doc["content"],
                        relevance_score=doc["relevance_score"],
                        rerank_score=doc.get("rerank_score"),
                        metadata=doc.get("metadata", {}),
                    )
                )
            entries.append(FixtureEntry(match=item["match"], chunks=chunks))
        return cls(fixtures=entries)
