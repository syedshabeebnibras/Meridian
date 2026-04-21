"""Scorers — classifier exact-match and Q&A faithfulness.

Phase 2 faithfulness is a *provisional* heuristic judge: it checks citation
coverage and penalises obvious hallucinations. Phase 5 calibrates a real
LLM-as-judge against 50+ human labels with kappa > 0.6 (Section 10).
"""

from __future__ import annotations

from typing import Any, Protocol

from meridian_contracts import ModelResponse
from pydantic import BaseModel, ConfigDict, Field

from meridian_evaluator.datasets import ClassifierExample, GoldenQAExample


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    value: float = Field(ge=0.0, le=1.0)
    details: dict[str, Any] = Field(default_factory=dict)


class Scorer(Protocol):
    name: str

    def score(self, example: Any, response: ModelResponse) -> Score: ...


# ---------------------------------------------------------------------------
# Classifier — exact-match on intent (+ tier bonus if provided).
# ---------------------------------------------------------------------------
class ClassifierScorer:
    name = "classifier_accuracy"

    def score(self, example: ClassifierExample, response: ModelResponse) -> Score:
        if not isinstance(response.content, dict):
            return Score(passed=False, value=0.0, details={"reason": "non-dict content"})
        predicted_intent = response.content.get("intent")
        predicted_tier = response.content.get("model_tier")

        intent_match = str(predicted_intent) == example.expected_intent.value
        details: dict[str, Any] = {
            "expected_intent": example.expected_intent.value,
            "predicted_intent": predicted_intent,
        }

        if example.expected_tier is not None:
            tier_match = str(predicted_tier) == example.expected_tier.value
            details["expected_tier"] = example.expected_tier.value
            details["predicted_tier"] = predicted_tier
            passed = intent_match and tier_match
            value = 1.0 if passed else (0.5 if intent_match else 0.0)
        else:
            passed = intent_match
            value = 1.0 if passed else 0.0

        return Score(passed=passed, value=value, details=details)


# ---------------------------------------------------------------------------
# Grounded Q&A — citation coverage + substring hints (Phase 2 placeholder).
# ---------------------------------------------------------------------------
class FaithfulnessScorer:
    """Placeholder judge — citation coverage + 'I don't know' detection.

    Flags a response as failing if: (a) it claims knowledge but misses a
    required citation, (b) it fabricates a citation not in the retrieved
    docs, or (c) it refuses when a golden answer exists.
    """

    name = "faithfulness"

    def score(self, example: GoldenQAExample, response: ModelResponse) -> Score:
        if not isinstance(response.content, dict):
            return Score(passed=False, value=0.0, details={"reason": "non-dict content"})

        answer = str(response.content.get("answer", ""))
        citations = response.content.get("citations", []) or []
        if not isinstance(citations, list):
            citations = []

        details: dict[str, Any] = {
            "expected_citations": example.expected_citations,
            "cited_titles": [c.get("source_title") for c in citations if isinstance(c, dict)],
        }

        # If the model refused but a golden answer exists, that's a fail.
        refused = "I don't have enough information" in answer
        if refused and example.golden_answer:
            return Score(
                passed=False, value=0.0, details={**details, "reason": "unjustified refusal"}
            )

        if not example.expected_citations:
            # No expected citations — any plausible grounded answer passes.
            return Score(passed=bool(answer), value=1.0 if answer else 0.0, details=details)

        required = set(example.expected_citations)
        actual = {c.get("source_title") for c in citations if isinstance(c, dict)}
        matched = required & actual
        # Hallucination check — cited a title that wasn't retrieved.
        retrieved_titles = {d.title for d in example.retrieved_docs}
        hallucinated = actual - retrieved_titles
        details["hallucinated_citations"] = sorted(hallucinated)

        coverage = len(matched) / len(required) if required else 1.0
        hallucination_penalty = 0.5 if hallucinated else 0.0
        value = max(0.0, coverage - hallucination_penalty)
        passed = coverage >= 0.75 and not hallucinated
        details["coverage"] = coverage
        return Score(passed=passed, value=value, details=details)
