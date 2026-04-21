"""LLM-as-judge tests — rubric rendering, score parsing, kappa computation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from meridian_contracts import ModelRequest, ModelResponse, ModelUsage
from meridian_evaluator import (
    FaithfulnessJudge,
    JudgeScore,
    PairwiseJudge,
    PairwiseResult,
    RelevanceJudge,
    cohens_kappa,
)


@dataclass
class _ScriptedClient:
    response_content: dict[str, Any] | str
    last_request: ModelRequest | None = None

    def chat(self, request: ModelRequest) -> ModelResponse:
        self.last_request = request
        return ModelResponse(
            id="stub",
            model=request.model,
            content=self.response_content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


def test_faithfulness_judge_parses_score() -> None:
    client = _ScriptedClient(response_content={"score": 0.9, "reasoning": "claims match"})
    judge = FaithfulnessJudge(client=client)
    result = judge.score(
        answer="The SLA is 99.95%.",
        retrieved_docs_text="The SLA is 99.95% uptime.",
    )
    assert isinstance(result, JudgeScore)
    assert result.rubric == "faithfulness"
    assert result.value == 0.9
    assert "claims match" in result.reasoning
    # Confirm the template rendered — the rubric text should appear in the system message.
    assert client.last_request is not None
    system_msgs = [m for m in client.last_request.messages if m.role == "system"]
    assert system_msgs
    assert "faithfulness" in system_msgs[0].content.lower()
    assert "1.0:" in system_msgs[0].content


def test_faithfulness_judge_clamps_out_of_range_scores() -> None:
    from pydantic import ValidationError

    client = _ScriptedClient(response_content={"score": 1.5, "reasoning": "..."})
    judge = FaithfulnessJudge(client=client)
    with pytest.raises(ValidationError):  # Pydantic ge=/le= rejects > 1.0
        judge.score(answer="x", retrieved_docs_text="y")


def test_relevance_judge_parses_score() -> None:
    client = _ScriptedClient(response_content={"score": 0.75, "reasoning": "mostly answers"})
    judge = RelevanceJudge(client=client)
    result = judge.score(question="What's the SLA?", answer="Uptime is 99.95%.")
    assert result.value == 0.75
    assert result.rubric == "relevance"


def test_pairwise_judge_parses_winner() -> None:
    client = _ScriptedClient(response_content={"winner": "B", "reasoning": "B is more complete"})
    judge = PairwiseJudge(client=client)
    result = judge.score(question="q", answer_a="a1", answer_b="a2")
    assert isinstance(result, PairwiseResult)
    assert result.winner == "B"


def test_pairwise_judge_defaults_invalid_to_tie() -> None:
    client = _ScriptedClient(response_content={"winner": "C", "reasoning": "oops"})
    judge = PairwiseJudge(client=client)
    result = judge.score(question="q", answer_a="a", answer_b="b")
    assert result.winner == "tie"


def test_pairwise_judge_handles_string_content_json() -> None:
    client = _ScriptedClient(response_content='{"winner":"A","reasoning":"a is grounded"}')
    judge = PairwiseJudge(client=client)
    result = judge.score(question="q", answer_a="a", answer_b="b")
    assert result.winner == "A"


# ---- Cohen's kappa --------------------------------------------------------
def test_cohens_kappa_perfect_agreement() -> None:
    # Identical scores → kappa = 1.0
    scores = [0.1, 0.5, 0.9, 0.3, 0.7]
    assert cohens_kappa(scores, scores) == 1.0


def test_cohens_kappa_around_section_10_gate() -> None:
    # Construct a case where judge + human agree on most but not all.
    judge = [0.9, 0.8, 0.3, 0.7, 0.9, 0.2, 0.85, 0.9, 0.1, 0.7]
    human = [0.9, 0.9, 0.3, 0.7, 0.9, 0.3, 0.9, 0.85, 0.1, 0.75]
    k = cohens_kappa(judge, human)
    # Expect reasonable agreement; don't hard-code exact value — just > 0.6.
    assert k > 0.6, f"expected kappa > 0.6 but got {k:.3f}"


def test_cohens_kappa_disagreement_below_gate() -> None:
    judge = [0.9, 0.1, 0.9, 0.1, 0.9, 0.1]
    human = [0.1, 0.9, 0.1, 0.9, 0.1, 0.9]
    k = cohens_kappa(judge, human)
    assert k < 0.0


def test_cohens_kappa_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        cohens_kappa([0.1, 0.2], [0.1])


def test_cohens_kappa_rejects_empty() -> None:
    with pytest.raises(ValueError):
        cohens_kappa([], [])
