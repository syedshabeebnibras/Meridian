"""Regressor integration tests — offline (stub client) flow.

Live-API tests live outside pytest and run via `make regression`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelTier,
    PromptTemplate,
    TokenBudget,
)
from meridian_evaluator import (
    ClassifierScorer,
    FaithfulnessScorer,
    Regressor,
    StubModelClient,
    load_dataset,
)
from meridian_evaluator.regressor import TIER_ALIAS

REPO_ROOT = Path(__file__).resolve().parents[3]


def _template_from_file(name: str) -> PromptTemplate:
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
            environment="test",
            status=ActivationStatus.DRAFT,
            canary_percentage=0,
            activated_at=datetime.now(tz=UTC),
            activated_by="t@t.com",
        ),
    )


def _stub_from_dataset(dataset: object, template: PromptTemplate) -> StubModelClient:
    client = StubModelClient()
    for ex in dataset.examples:  # type: ignore[attr-defined]
        if ex.stub_response is None:
            pytest.fail(f"example {ex.input!r} missing stub_response")
        client.register(
            model=TIER_ALIAS[template.model_tier],
            user_content_fragment=ex.input[:40],
            content=ex.stub_response.content,
            latency_ms=ex.stub_response.latency_ms,
        )
    return client


def test_classifier_dataset_hits_exit_criteria() -> None:
    dataset = load_dataset(REPO_ROOT / "datasets" / "classifier_v1.yaml")
    template = _template_from_file("classifier")
    client = _stub_from_dataset(dataset, template)
    regressor = Regressor(template=template, client=client, scorer=ClassifierScorer())

    result = regressor.run(dataset)

    # Phase 2 exit criterion for classifier: pass rate >= 80%.
    assert result.pass_rate >= 0.80, (
        f"classifier pass rate {result.pass_rate:.2%} < 80% on {result.total} examples"
    )


def test_grounded_qa_dataset_hits_exit_criteria() -> None:
    dataset = load_dataset(REPO_ROOT / "datasets" / "grounded_qa_v1.yaml")
    template = _template_from_file("grounded_qa")
    client = _stub_from_dataset(dataset, template)
    regressor = Regressor(template=template, client=client, scorer=FaithfulnessScorer())

    result = regressor.run(dataset)

    # Phase 2 exit criterion for Q&A: mean faithfulness >= 0.75.
    assert result.mean_score >= 0.75, (
        f"grounded_qa mean score {result.mean_score:.3f} < 0.75 on {result.total} examples"
    )


def test_regressor_produces_per_example_results() -> None:
    dataset = load_dataset(REPO_ROOT / "datasets" / "classifier_v1.yaml")
    template = _template_from_file("classifier")
    client = _stub_from_dataset(dataset, template)
    regressor = Regressor(template=template, client=client, scorer=ClassifierScorer())

    result = regressor.run(dataset)
    assert result.total == len(dataset.examples)
    assert len(result.examples) == result.total
    for example_result in result.examples:
        assert "input" in example_result
        assert "passed" in example_result
        assert "score" in example_result
        assert "details" in example_result


def test_classifier_scorer_awards_partial_credit_for_intent_only() -> None:
    # When tier is wrong but intent is right, the classifier scorer should
    # report 0.5 (not a pass, not a total fail).
    from meridian_contracts import Intent, ModelResponse, ModelUsage
    from meridian_evaluator.datasets import ClassifierExample

    scorer = ClassifierScorer()
    ex = ClassifierExample(
        input="What is the SLA?",
        expected_intent=Intent.GROUNDED_QA,
        expected_tier=ModelTier.MID,
    )
    response = ModelResponse(
        id="stub",
        model="meridian-mid",
        content={"intent": "grounded_qa", "confidence": 0.9, "model_tier": "small"},
        usage=ModelUsage(input_tokens=0, output_tokens=0),
        latency_ms=10,
    )
    score = scorer.score(ex, response)
    assert score.passed is False
    assert score.value == 0.5


def test_faithfulness_scorer_flags_refusal_when_answer_exists() -> None:
    from meridian_contracts import ModelResponse, ModelUsage
    from meridian_evaluator.datasets import GoldenQAExample

    scorer = FaithfulnessScorer()
    ex = GoldenQAExample(
        input="What's the uptime SLA?",
        retrieved_docs=[],
        golden_answer="99.9%",
        expected_citations=["SLA doc"],
    )
    response = ModelResponse(
        id="stub",
        model="meridian-mid",
        content={
            "reasoning": "",
            "answer": "I don't have enough information to answer this reliably.",
            "citations": [],
            "confidence": 0.1,
            "needs_escalation": False,
        },
        usage=ModelUsage(input_tokens=0, output_tokens=0),
        latency_ms=10,
    )
    score = scorer.score(ex, response)
    assert score.passed is False
    assert score.details["reason"] == "unjustified refusal"


def test_faithfulness_scorer_penalises_hallucinated_citation() -> None:
    from meridian_contracts import ModelResponse, ModelUsage
    from meridian_evaluator.datasets import GoldenQAExample, _RetrievedDocFixture

    scorer = FaithfulnessScorer()
    ex = GoldenQAExample(
        input="Q",
        retrieved_docs=[
            _RetrievedDocFixture(
                title="Real Doc", url="https://example.com/r", content="stuff", relevance=0.9
            )
        ],
        golden_answer="A",
        expected_citations=["Real Doc"],
    )
    response = ModelResponse(
        id="stub",
        model="meridian-mid",
        content={
            "reasoning": "",
            "answer": "See [DOC-1] and [DOC-2].",
            "citations": [
                {"doc_index": 1, "source_title": "Real Doc"},
                {"doc_index": 2, "source_title": "Fabricated Doc"},
            ],
            "confidence": 0.9,
            "needs_escalation": False,
        },
        usage=ModelUsage(input_tokens=0, output_tokens=0),
        latency_ms=10,
    )
    score = scorer.score(ex, response)
    assert score.passed is False  # hallucinated citation is a fail
    assert "Fabricated Doc" in score.details["hallucinated_citations"]
