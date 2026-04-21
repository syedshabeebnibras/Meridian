"""Tests for MockRetrievalClient — match logic + YAML loading."""

from __future__ import annotations

from pathlib import Path

from meridian_contracts import RetrievedChunk
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry
from pydantic import HttpUrl


def _chunk(i: int, title: str, content: str = "content") -> RetrievedChunk:
    return RetrievedChunk(
        index=i,
        chunk_id=f"c{i}",
        source_title=title,
        source_url=HttpUrl("https://example.com/"),
        content=content,
        relevance_score=0.9,
    )


def test_first_matching_entry_wins() -> None:
    client = MockRetrievalClient(
        fixtures=[
            FixtureEntry(match="database", chunks=[_chunk(1, "DB Runbook")]),
            FixtureEntry(match="sla", chunks=[_chunk(2, "SLA Policy")]),
        ]
    )
    result = client.retrieve("What's the SLA for our database?")
    assert [c.source_title for c in result.results] == ["DB Runbook"]


def test_empty_match_is_fallback() -> None:
    client = MockRetrievalClient(
        fixtures=[
            FixtureEntry(match="specific", chunks=[_chunk(1, "Specific")]),
            FixtureEntry(match="", chunks=[_chunk(2, "Fallback")]),
        ]
    )
    result = client.retrieve("something unrelated")
    assert [c.source_title for c in result.results] == ["Fallback"]


def test_no_match_returns_empty() -> None:
    client = MockRetrievalClient(fixtures=[FixtureEntry(match="never", chunks=[_chunk(1, "Nope")])])
    result = client.retrieve("anything else")
    assert result.results == []
    assert result.total_chunks_retrieved == 0


def test_top_k_limits_chunks() -> None:
    client = MockRetrievalClient(
        fixtures=[
            FixtureEntry(
                match="many",
                chunks=[_chunk(i, f"Doc {i}") for i in range(1, 6)],
            )
        ]
    )
    result = client.retrieve("give me many docs", top_k=2)
    assert len(result.results) == 2


def test_from_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "fixtures.yaml"
    yaml_path.write_text(
        """
fixtures:
  - match: P1 outage
    chunks:
      - source_title: "Incident Runbook"
        source_url: "https://example.com/r"
        content: "Page on-call immediately."
        relevance_score: 0.95
""".strip()
    )
    client = MockRetrievalClient.from_yaml(yaml_path)
    result = client.retrieve("What's the P1 outage procedure?")
    assert len(result.results) == 1
    assert result.results[0].source_title == "Incident Runbook"
    assert result.results[0].relevance_score == 0.95
