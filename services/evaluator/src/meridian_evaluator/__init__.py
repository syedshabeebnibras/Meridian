"""Meridian evaluator.

Phase 2 ships the regression runner that flows a labeled dataset through
assembler → model client → scorer and produces a report. The offline path
uses StubModelClient (scripted responses) so CI can run without live API
keys; live runs hit the LiteLLM gateway.
"""

from meridian_evaluator.datasets import (
    ClassifierExample,
    Dataset,
    GoldenQAExample,
    load_dataset,
)
from meridian_evaluator.judges import (
    FaithfulnessJudge,
    JudgeScore,
    PairwiseJudge,
    PairwiseResult,
    RelevanceJudge,
    cohens_kappa,
)
from meridian_evaluator.online import OnlineEvalSampler, SampleDecision
from meridian_evaluator.regressor import RegressionResult, RegressionRun, Regressor
from meridian_evaluator.reports import render_markdown_report
from meridian_evaluator.scorers import (
    ClassifierScorer,
    FaithfulnessScorer,
    Score,
    Scorer,
)
from meridian_evaluator.shadow import ShadowReport, ShadowRunner, ShadowTrial
from meridian_evaluator.stub_client import StubModelClient

__all__ = [
    "ClassifierExample",
    "ClassifierScorer",
    "Dataset",
    "FaithfulnessJudge",
    "FaithfulnessScorer",
    "GoldenQAExample",
    "JudgeScore",
    "OnlineEvalSampler",
    "PairwiseJudge",
    "PairwiseResult",
    "RegressionResult",
    "RegressionRun",
    "Regressor",
    "RelevanceJudge",
    "SampleDecision",
    "Score",
    "Scorer",
    "ShadowReport",
    "ShadowRunner",
    "ShadowTrial",
    "StubModelClient",
    "cohens_kappa",
    "load_dataset",
    "render_markdown_report",
]
