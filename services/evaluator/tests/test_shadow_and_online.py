"""Shadow runner + online sampler tests."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from meridian_contracts import (
    ModelRequest,
    ModelResponse,
    ModelUsage,
    OrchestrationState,
    OrchestratorPhase,
    TimingsMs,
    UserRequest,
)
from meridian_evaluator import (
    FaithfulnessJudge,
    OnlineEvalSampler,
    PairwiseJudge,
    RelevanceJudge,
    ShadowRunner,
)


@dataclass
class _Client:
    content: dict[str, Any]

    def chat(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            id="s",
            model=request.model,
            content=self.content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


class _FakeReply:
    def __init__(self, answer: str, latency_ms: int, *, error_message: str | None = None) -> None:
        self.model_response = ModelResponse(
            id="r",
            model="meridian-mid",
            content={
                "answer": answer,
                "citations": [],
                "confidence": 0.9,
                "needs_escalation": False,
                "reasoning": "",
            },
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=latency_ms,
        )
        self.orchestration_state = OrchestrationState(
            request_id="r",
            current_state=OrchestratorPhase.COMPLETED,
            timings_ms=TimingsMs(total=latency_ms),
        )
        self.error_message = error_message


class _FakeOrchestrator:
    def __init__(self, answer: str, latency_ms: int) -> None:
        self._answer = answer
        self._latency = latency_ms

    def handle(self, request: UserRequest) -> _FakeReply:
        return _FakeReply(answer=self._answer, latency_ms=self._latency)


def _request(q: str = "What's the SLA?") -> UserRequest:
    return UserRequest(request_id="req_test001", user_id="u", session_id="s", query=q)


# ---- Shadow runner --------------------------------------------------------
def test_shadow_runner_picks_b_when_judge_says_b() -> None:
    judge = PairwiseJudge(client=_Client({"winner": "B", "reasoning": "B better"}))
    orch_a = _FakeOrchestrator("old answer", latency_ms=500)
    orch_b = _FakeOrchestrator("new answer", latency_ms=400)
    runner = ShadowRunner(orchestrator_a=orch_a, orchestrator_b=orch_b, judge=judge)

    report = runner.run([_request("q1"), _request("q2"), _request("q3")])

    assert report.total == 3
    assert report.wins_b == 3
    assert report.wins_a == 0
    assert report.non_regression_rate == 1.0
    assert report.passes_95_gate is True
    assert report.avg_latency_ms_b == 400.0


def test_shadow_runner_fails_gate_when_b_mostly_loses() -> None:
    # Judge says A wins every time → B never non-regressing.
    judge = PairwiseJudge(client=_Client({"winner": "A", "reasoning": "A better"}))
    orch_a = _FakeOrchestrator("a", latency_ms=300)
    orch_b = _FakeOrchestrator("b", latency_ms=300)
    runner = ShadowRunner(orchestrator_a=orch_a, orchestrator_b=orch_b, judge=judge)

    report = runner.run([_request(f"q{i}") for i in range(10)])
    assert report.wins_a == 10
    assert report.non_regression_rate == 0.0
    assert report.passes_95_gate is False


def test_shadow_runner_counts_ties_as_non_regression() -> None:
    judge = PairwiseJudge(client=_Client({"winner": "tie", "reasoning": "same"}))
    orch_a = _FakeOrchestrator("a", latency_ms=300)
    orch_b = _FakeOrchestrator("b", latency_ms=300)
    runner = ShadowRunner(orchestrator_a=orch_a, orchestrator_b=orch_b, judge=judge)

    report = runner.run([_request(f"q{i}") for i in range(5)])
    assert report.ties == 5
    assert report.passes_95_gate is True


# ---- Online sampler -------------------------------------------------------
def test_sampler_respects_sample_rate() -> None:
    # Seeded RNG → deterministic. First 3 rolls with seed 42 are < 0.1 half
    # the time; we only assert that the gate behaves monotonically.
    rng = random.Random(42)
    sampler = OnlineEvalSampler(
        faithfulness=FaithfulnessJudge(client=_Client({"score": 0.9, "reasoning": ""})),
        sample_rate=0.2,
        rng=rng,
    )
    decisions = [sampler.should_sample() for _ in range(1000)]
    sampled = sum(1 for d in decisions if d.sampled)
    # Expect ~200 out of 1000 with rate=0.2; allow wide tolerance.
    assert 150 < sampled < 250


def test_sampler_score_produces_evaluation_record() -> None:
    sampler = OnlineEvalSampler(
        faithfulness=FaithfulnessJudge(client=_Client({"score": 0.87, "reasoning": "ok"})),
        relevance=RelevanceJudge(client=_Client({"score": 0.9, "reasoning": "relevant"})),
        sample_rate=1.0,
    )
    record = sampler.score(
        request_id="req_abc",
        question="What's up?",
        answer="not much",
        retrieved_docs_text="",
        prompt_version="grounded_qa_v1",
        model_used="meridian-mid",
        latency_ms=1234,
        total_cost_usd=0.012,
    )
    assert record.eval_type.value == "online_sample"
    assert record.scores.faithfulness == 0.87
    assert record.scores.relevance == 0.9
    assert record.latency_ms == 1234
    assert record.prompt_version == "grounded_qa_v1"


def test_sampler_without_judges_returns_empty_scores() -> None:
    sampler = OnlineEvalSampler(sample_rate=1.0)
    record = sampler.score(
        request_id="req_abc",
        question="q",
        answer="a",
        retrieved_docs_text="",
        prompt_version="v1",
        model_used="meridian-mid",
        latency_ms=100,
        total_cost_usd=0.001,
    )
    assert record.scores.faithfulness is None
    assert record.scores.relevance is None
