"""Semantic response cache — Section 5 three-layer cache, Section 9 mode 10.

Cosine >= 0.95 threshold. 1-hour TTL. Partition key is a hash of the
retrieved-doc-id set so that two queries answered against different
docs don't share a cache entry.

Protocol is embedding-model-agnostic; Phase 9 plugs pgvector with
OpenAI or Anthropic embeddings depending on what the cost/latency
budget says.
"""

from meridian_semantic_cache.cache import (
    CacheHit,
    CacheLookupResult,
    CacheMiss,
    SemanticCache,
)
from meridian_semantic_cache.embedding import EmbeddingModel, OpenAIEmbedding, StaticEmbedding
from meridian_semantic_cache.memory import InMemorySemanticCache
from meridian_semantic_cache.postgres import PostgresSemanticCache

__all__ = [
    "CacheHit",
    "CacheLookupResult",
    "CacheMiss",
    "EmbeddingModel",
    "InMemorySemanticCache",
    "OpenAIEmbedding",
    "PostgresSemanticCache",
    "SemanticCache",
    "StaticEmbedding",
]
