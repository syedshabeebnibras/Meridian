"""Pins the contract that semantic-cache partition keys are
workspace-aware.

Without this, two tenants whose external RAG returns the same chunk IDs
could collide on a cache hit. The orchestrator's
``_semantic_cache_partition_key`` now derives the key from
``ws:<workspace>|<sorted chunk ids>``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelTier,
    PromptTemplate,
    TokenBudget,
    UserRequest,
)
from meridian_orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
)
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry


class _NoopTemplates(TemplateProvider):
    def get_active(self, name: str, environment: str) -> PromptTemplate:
        return PromptTemplate(
            name=name,
            version=1,
            model_tier=ModelTier.MID,
            min_model="meridian-mid",
            template="t",
            parameters=[],
            schema_ref="x",
            token_budget=TokenBudget(prompt_tokens=10, completion_tokens=10),
            cache_control=CacheControl(),
            activation=ActivationInfo(
                environment=environment,
                status=ActivationStatus.DRAFT,
                canary_percentage=0,
                activated_at=datetime.now(tz=UTC),
                activated_by="t@t",
            ),
        )


class _NoopModel:
    def chat(self, request: Any) -> Any:
        raise RuntimeError("not invoked in this test")


@dataclass
class _Chunk:
    chunk_id: str


def _orch() -> Orchestrator:
    return Orchestrator(
        templates=_NoopTemplates(),
        retrieval=MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])]),
        model_client=_NoopModel(),
        config=OrchestratorConfig(environment="test"),
    )


def _request(workspace_id: str | None) -> UserRequest:
    metadata = {"workspace_id": workspace_id} if workspace_id else {}
    return UserRequest(
        request_id="req_test1",
        user_id="u",
        session_id="s",
        query="q",
        conversation_history=[],
        metadata=metadata,
    )


def test_workspace_id_is_part_of_partition_key() -> None:
    orchestrator = _orch()
    docs = [_Chunk(chunk_id="c1"), _Chunk(chunk_id="c2")]
    key = orchestrator._semantic_cache_partition_key(docs, _request("ws-A"))
    assert key.startswith("ws:ws-A|")
    assert "c1" in key and "c2" in key


def test_two_workspaces_with_same_chunks_get_distinct_partitions() -> None:
    """Cross-tenant collision check: same chunks, different workspaces → keys differ."""
    orchestrator = _orch()
    docs = [_Chunk(chunk_id="shared-1"), _Chunk(chunk_id="shared-2")]
    key_a = orchestrator._semantic_cache_partition_key(docs, _request("ws-A"))
    key_b = orchestrator._semantic_cache_partition_key(docs, _request("ws-B"))
    assert key_a != key_b


def test_no_workspace_metadata_falls_back_to_none_sentinel() -> None:
    orchestrator = _orch()
    key = orchestrator._semantic_cache_partition_key([], _request(workspace_id=None))
    assert key == "ws:none|no-docs"


def test_no_docs_keeps_workspace_in_key() -> None:
    """When retrieval returned 0 chunks, workspace still partitions the cache."""
    orchestrator = _orch()
    key_a = orchestrator._semantic_cache_partition_key([], _request("ws-A"))
    key_b = orchestrator._semantic_cache_partition_key([], _request("ws-B"))
    assert key_a == "ws:ws-A|no-docs"
    assert key_b == "ws:ws-B|no-docs"
    assert key_a != key_b
