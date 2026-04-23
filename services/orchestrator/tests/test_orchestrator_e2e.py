"""End-to-end orchestrator tests + failover simulation + p95 latency check.

Satisfies Phase 3 exit criteria (Section 12):
  - end-to-end request flow works with mock retrieval
  - failover tested with simulated provider outage
  - p95 latency < 4s on test queries
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelRequest,
    ModelResponse,
    ModelTier,
    ModelUsage,
    PromptTemplate,
    TokenBudget,
    UserRequest,
)
from meridian_model_gateway import CircuitBreaker, RetryingClient, RetryPolicy
from meridian_orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorStatus,
    TemplateProvider,
)
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry
from pydantic import HttpUrl

REPO_ROOT = Path(__file__).resolve().parents[3]


class FileTemplateProvider(TemplateProvider):
    """Reads prompts/<name>/v1.yaml — no DB dependency in tests."""

    def get_active(self, name: str, environment: str) -> PromptTemplate:
        path = REPO_ROOT / "prompts" / name / "v1.yaml"
        raw = yaml.safe_load(path.read_text())
        return PromptTemplate(
            name=raw["name"],
            version=1,
            model_tier=ModelTier(raw["model_tier"]),
            min_model=raw["min_model"],
            template=raw["template"],
            parameters=raw["parameters"],
            schema_ref=raw["schema_ref"],
            few_shot_dataset=raw.get("few_shot_dataset"),
            token_budget=TokenBudget.model_validate(raw["token_budget"]),
            cache_control=CacheControl.model_validate(raw["cache_control"]),
            activation=ActivationInfo(
                environment=environment,
                status=ActivationStatus.DRAFT,
                canary_percentage=0,
                activated_at=datetime.now(tz=UTC),
                activated_by="t@t.com",
            ),
        )


class ScriptedClient:
    """A ModelClient that returns content keyed by alias.

    Use `fail_next(fn)` to inject transient failures (simulating a provider outage).
    """

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[ModelRequest] = []
        self._fail_with: list[Callable[[], None]] = []

    def fail_next(self, factory: Callable[[], None]) -> None:
        self._fail_with.append(factory)

    def chat(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if self._fail_with:
            failure = self._fail_with.pop(0)
            failure()
        content = self._responses.get(request.model)
        if content is None:
            raise KeyError(f"no scripted response for {request.model!r}")
        return ModelResponse(
            id=f"t_{len(self.calls)}",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


def _chunk(index: int, title: str, content: str):  # type: ignore[no-untyped-def]
    from meridian_contracts import RetrievedChunk

    return RetrievedChunk(
        index=index,
        chunk_id=f"c{index}",
        source_title=title,
        source_url=HttpUrl("https://example.com/"),
        content=content,
        relevance_score=0.9,
    )


def _mock_retrieval() -> MockRetrievalClient:
    return MockRetrievalClient(
        fixtures=[
            FixtureEntry(
                match="P1 outage",
                chunks=[
                    _chunk(1, "Incident Response Runbook", "Page the on-call SRE immediately."),
                    _chunk(2, "On-Call Procedures 2026", "Status updates every 15 minutes."),
                ],
            ),
            FixtureEntry(match="", chunks=[]),
        ]
    )


def _orchestrator(scripted: ScriptedClient) -> Orchestrator:
    return Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=scripted,
        config=OrchestratorConfig(environment="test"),
    )


def _user_request(query: str = "What is the escalation procedure for a P1 outage?") -> UserRequest:
    return UserRequest(
        request_id="req_test001",
        user_id="u_alice",
        session_id="s_1",
        query=query,
    )


def _valid_qa_content() -> dict[str, Any]:
    return {
        "reasoning": "DOC-1 + DOC-2 cover it.",
        "answer": (
            "Page the on-call SRE immediately [DOC-1]. Post status updates every 15 "
            "minutes until resolution [DOC-2]."
        ),
        "citations": [
            {
                "doc_index": 1,
                "source_title": "Incident Response Runbook",
                "relevant_excerpt": "Page the on-call SRE immediately...",
            },
            {
                "doc_index": 2,
                "source_title": "On-Call Procedures 2026",
                "relevant_excerpt": "Status updates every 15 minutes...",
            },
        ],
        "confidence": 0.93,
        "needs_escalation": False,
    }


# ---- Happy-path E2E --------------------------------------------------------
def test_end_to_end_happy_path() -> None:
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    reply = _orchestrator(scripted).handle(_user_request())

    assert reply.status is OrchestratorStatus.OK
    assert reply.model_response is not None
    assert reply.orchestration_state.classification is not None
    assert reply.orchestration_state.classification.intent.value == "grounded_qa"
    assert reply.orchestration_state.retrieval is not None
    assert reply.orchestration_state.retrieval.chunks_retrieved == 2
    assert reply.validation is not None
    assert reply.validation.valid is True


def test_refusal_when_classifier_confidence_too_low() -> None:
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.4, "model_tier": "mid"},
        }
    )
    reply = _orchestrator(scripted).handle(_user_request("fuzzy question"))
    assert reply.status is OrchestratorStatus.REFUSED
    assert reply.model_response is None


def test_routing_bumps_tier_on_mid_confidence() -> None:
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.7, "model_tier": "small"},
            # after bump: small → mid
            "meridian-mid": _valid_qa_content(),
        }
    )
    reply = _orchestrator(scripted).handle(_user_request())
    assert reply.status is OrchestratorStatus.OK
    mid_calls = [c for c in scripted.calls if c.model == "meridian-mid"]
    assert len(mid_calls) == 1


# ---- Validation retry ------------------------------------------------------
def test_validation_failure_triggers_corrective_retry() -> None:
    invalid = {
        "reasoning": "x",
        "answer": "See [DOC-9] — never retrieved.",
        "citations": [],
        "confidence": 0.9,
        "needs_escalation": False,
    }
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": invalid,
        }
    )
    reply = _orchestrator(scripted).handle(_user_request())
    mid_calls = [c for c in scripted.calls if c.model == "meridian-mid"]
    assert len(mid_calls) == 2
    assert reply.status is OrchestratorStatus.FAILED


# ---- Failover simulation ---------------------------------------------------
def test_failover_retries_transient_429s() -> None:
    """A 429 from the provider triggers the retry layer transparently."""

    def raise_429() -> None:
        req = httpx.Request("POST", "http://x/v1/chat/completions")
        resp = httpx.Response(429, content=b'{"error":"rate"}')
        raise httpx.HTTPStatusError("rl", request=req, response=resp)

    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    scripted.fail_next(raise_429)
    scripted.fail_next(raise_429)

    retrying = RetryingClient(
        inner=scripted,
        policy=RetryPolicy(jitter_ratio=0.0),
        sleep=lambda _: None,
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=retrying,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request())

    assert reply.status is OrchestratorStatus.OK
    # classifier + 3 mid-attempts (2 failures + 1 success) = 4 total calls.
    assert len(scripted.calls) == 4


def test_degraded_mode_when_circuit_is_open() -> None:
    """When the circuit is open before dispatch, the orchestrator degrades."""

    class AlwaysFail:
        def chat(self, _: ModelRequest) -> ModelResponse:
            raise RuntimeError("provider is burning")

    breaker = CircuitBreaker(
        inner=AlwaysFail(),
        failure_threshold=3,
        window_seconds=60.0,
        cooldown_seconds=30.0,
    )
    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.chat(
                ModelRequest(
                    model="meridian-small",
                    messages=[{"role": "user", "content": "x"}],
                    max_tokens=16,
                )
            )
    assert breaker.state.value == "open"

    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=breaker,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request())
    assert reply.status is OrchestratorStatus.DEGRADED
    assert reply.error_message is not None
    assert "temporarily unavailable" in reply.error_message.lower()


# ---- Latency -- exit criterion "p95 latency < 4s" -------------------------
def test_p95_latency_under_four_seconds() -> None:
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    orch = _orchestrator(scripted)

    samples: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        reply = orch.handle(_user_request())
        samples.append(time.perf_counter() - started)
        assert reply.status is OrchestratorStatus.OK

    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 4.0, f"p95 latency {p95:.3f}s >= 4s on stub run"
    assert statistics.mean(samples) < 0.2


# ---- Semantic cache (B1) --------------------------------------------------
def test_semantic_cache_hit_short_circuits_dispatch() -> None:
    """An identical follow-up query served from retrieval with the same docs
    should hit the cache and skip the mid-tier model call."""
    from meridian_semantic_cache import InMemorySemanticCache, StaticEmbedding

    cache = InMemorySemanticCache(embedding_model=StaticEmbedding())
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=scripted,
        semantic_cache=cache,
        config=OrchestratorConfig(environment="test"),
    )

    # First call: MISS → model is invoked → stored.
    reply1 = orch.handle(_user_request())
    assert reply1.status is OrchestratorStatus.OK
    first_mid_calls = len([c for c in scripted.calls if c.model == "meridian-mid"])
    assert first_mid_calls == 1

    # Second call: HIT → short-circuit; mid-tier count must NOT grow.
    reply2 = orch.handle(_user_request())
    assert reply2.status is OrchestratorStatus.OK
    second_mid_calls = len([c for c in scripted.calls if c.model == "meridian-mid"])
    assert second_mid_calls == 1, "semantic cache should have skipped the second mid call"
    # Cached reply reports zero cost.
    assert reply2.cost_usd == 0.0
    assert reply2.model_response is not None
    assert reply2.model_response.model == "cache"


# ---- Cost circuit breaker (B4) --------------------------------------------
def test_cost_breaker_degrades_frontier_to_mid_when_open() -> None:
    """When the CostCircuitBreaker is open, a frontier-tier classification
    still gets served — just from the mid-tier model. The user gets an
    answer, we get to stop bleeding money."""
    from decimal import Decimal

    from meridian_cost_accounting import CostCircuitBreaker

    # Seed the breaker well past its budget so state == OPEN.
    breaker = CostCircuitBreaker(daily_budget_usd=Decimal("1"))
    breaker.record(Decimal("100"))  # 100x over budget
    assert breaker.state.value == "open"

    scripted = ScriptedClient(
        {
            # Classifier demands FRONTIER with high confidence.
            "meridian-small": {
                "intent": "grounded_qa",
                "confidence": 0.99,
                "model_tier": "frontier",
            },
            # Mid responds with a valid answer — this is what we should
            # actually call through to under an open breaker.
            "meridian-mid": _valid_qa_content(),
        }
    )

    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=scripted,
        cost_breaker=breaker,
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request())

    assert reply.status is OrchestratorStatus.OK
    # Frontier should have been skipped entirely.
    frontier_calls = [c for c in scripted.calls if c.model == "meridian-frontier"]
    mid_calls = [c for c in scripted.calls if c.model == "meridian-mid"]
    assert not frontier_calls, "frontier must be skipped when breaker is open"
    assert mid_calls, "mid must be called as fallback"
    # State exposes the degradation for observability.
    assert any("cost_breaker_open" in e for e in reply.orchestration_state.errors)


# ---- Session memory (B2) --------------------------------------------------
def test_session_store_hydrates_and_appends_on_success() -> None:
    """SessionStore: empty history triggers hydrate; successful reply appends
    the user+assistant turn so the next request sees conversation context."""
    from meridian_session_store import InMemorySessionStore

    store = InMemorySessionStore()
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=scripted,
        session_store=store,
        config=OrchestratorConfig(environment="test"),
    )

    # First call: store is empty, so nothing is hydrated; on OK both turns persist.
    reply1 = orch.handle(_user_request("What is the escalation procedure for a P1 outage?"))
    assert reply1.status is OrchestratorStatus.OK
    stored = store.get("s_1")
    assert [t.role for t in stored] == ["user", "assistant"]
    assert "P1 outage" in stored[0].content
    # Assistant turn is the natural-language answer, not the whole JSON blob.
    assert "on-call SRE" in stored[1].content


def test_session_store_hydrates_when_history_empty() -> None:
    """Pre-seeded store + empty inline history → history is hydrated into the
    UserRequest the assembler sees."""
    from meridian_contracts import ConversationTurn
    from meridian_session_store import InMemorySessionStore

    store = InMemorySessionStore()
    t0 = datetime.now(tz=UTC)
    store.append("s_1", ConversationTurn(role="user", content="earlier-user", timestamp=t0))
    store.append(
        "s_1", ConversationTurn(role="assistant", content="earlier-assistant", timestamp=t0)
    )

    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=scripted,
        session_store=store,
        config=OrchestratorConfig(environment="test"),
    )

    reply = orch.handle(_user_request())
    assert reply.status is OrchestratorStatus.OK
    # The assembler received the hydrated history — it ends up baked into the
    # prompt messages shipped to the mid-tier model. `earlier-user` should
    # appear somewhere in the prompt text.
    mid_calls = [c for c in scripted.calls if c.model == "meridian-mid"]
    assert mid_calls, "expected at least one mid-tier call"
    prompt_text = "\n".join(str(m) for call in mid_calls for m in call.messages)
    assert "earlier-user" in prompt_text


def test_session_store_skipped_when_history_provided_inline() -> None:
    """An explicit conversation_history on the request short-circuits hydration."""
    from meridian_contracts import ConversationTurn
    from meridian_session_store import InMemorySessionStore

    store = InMemorySessionStore()
    # Pre-seed the store with one turn that SHOULD NOT be loaded.
    store.append(
        "s_1",
        ConversationTurn(role="user", content="SHOULD-NOT-LEAK", timestamp=datetime.now(tz=UTC)),
    )
    scripted = ScriptedClient(
        {
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": _valid_qa_content(),
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_mock_retrieval(),
        model_client=scripted,
        session_store=store,
        config=OrchestratorConfig(environment="test"),
    )
    req = UserRequest(
        request_id="req_inline",
        user_id="u_alice",
        session_id="s_1",
        query="P1 outage?",
        conversation_history=[
            ConversationTurn(
                role="user", content="earlier turn", timestamp=datetime.now(tz=UTC)
            )
        ],
    )
    reply = orch.handle(req)
    assert reply.status is OrchestratorStatus.OK
    # After success the store is still appended to — but the leaked content
    # must not have reached the model.
    for call in scripted.calls:
        assert "SHOULD-NOT-LEAK" not in str(call)
