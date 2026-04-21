"""Retrieval result contract — Section 8.

Meridian consumes retrieval from the RAG pipeline (owned by Data Platform).
This contract is the agreed-upon wire format.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    chunk_id: str
    source_title: str
    source_url: HttpUrl
    content: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    query_rewritten: str
    results: list[RetrievedChunk]
    total_chunks_retrieved: int = Field(ge=0)
    total_after_rerank: int = Field(ge=0)
    retrieval_latency_ms: int = Field(ge=0)
