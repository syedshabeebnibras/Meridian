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
from meridian_evaluator.regressor import RegressionResult, RegressionRun, Regressor
from meridian_evaluator.reports import render_markdown_report
from meridian_evaluator.scorers import (
    ClassifierScorer,
    FaithfulnessScorer,
    Score,
    Scorer,
)
from meridian_evaluator.stub_client import StubModelClient

__all__ = [
    "ClassifierExample",
    "ClassifierScorer",
    "Dataset",
    "FaithfulnessScorer",
    "GoldenQAExample",
    "RegressionResult",
    "RegressionRun",
    "Regressor",
    "Score",
    "Scorer",
    "StubModelClient",
    "load_dataset",
    "render_markdown_report",
]
