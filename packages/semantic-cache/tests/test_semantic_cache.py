"""InMemorySemanticCache tests — store, lookup, partition isolation, TTL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from meridian_semantic_cache import (
    CacheHit,
    CacheMiss,
    InMemorySemanticCache,
    StaticEmbedding,
)


def _cache(ttl: float = 3600.0) -> InMemorySemanticCache:
    return InMemorySemanticCache(embedding_model=StaticEmbedding(), ttl_seconds=ttl)


def test_store_and_exact_lookup_hits() -> None:
    cache = _cache()
    cache.store(query="what's the SLA?", partition_key="p1", response_content={"answer": "99.95%"})
    result = cache.lookup(query="what's the SLA?", partition_key="p1")
    assert isinstance(result, CacheHit)
    assert result.response_content == {"answer": "99.95%"}
    assert result.similarity == 1.0


def test_miss_when_partition_differs() -> None:
    cache = _cache()
    cache.store(query="q", partition_key="p1", response_content="a")
    result = cache.lookup(query="q", partition_key="p2")
    assert isinstance(result, CacheMiss)


def test_miss_below_similarity_threshold() -> None:
    cache = _cache()
    cache.store(query="query one", partition_key="p1", response_content="a")
    result = cache.lookup(
        query="completely different query two", partition_key="p1", min_similarity=0.95
    )
    assert isinstance(result, CacheMiss)
    assert result.closest_similarity < 0.95


def test_miss_when_partition_is_empty() -> None:
    cache = _cache()
    result = cache.lookup(query="anything", partition_key="brand-new")
    assert isinstance(result, CacheMiss)
    assert result.reason == "no entries in partition"


def test_ttl_evicts_stale_entries() -> None:
    now = datetime.now(tz=UTC)
    current = now

    def clock() -> datetime:
        return current

    cache = InMemorySemanticCache(embedding_model=StaticEmbedding(), ttl_seconds=10, clock=clock)
    cache.store(query="q", partition_key="p", response_content="a")
    current = now + timedelta(seconds=30)
    result = cache.lookup(query="q", partition_key="p")
    assert isinstance(result, CacheMiss)


def test_stores_metadata_alongside_response() -> None:
    cache = _cache()
    cache.store(
        query="q",
        partition_key="p",
        response_content={"answer": "a"},
        metadata={"source_prompt_version": "grounded_qa_v3"},
    )
    result = cache.lookup(query="q", partition_key="p")
    assert isinstance(result, CacheHit)
    assert result.metadata["source_prompt_version"] == "grounded_qa_v3"


def test_lookup_min_similarity_override() -> None:
    cache = _cache()
    cache.store(query="one query", partition_key="p", response_content="a")
    # StaticEmbedding produces vectors whose cosine can be negative for
    # unrelated inputs, so use -1.0 to force any match into a hit — proves
    # the threshold parameter actually controls the decision.
    result = cache.lookup(query="another query entirely", partition_key="p", min_similarity=-1.0)
    assert isinstance(result, CacheHit)
