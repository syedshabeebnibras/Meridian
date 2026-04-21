"""Model-routing rules — exercise Section 7 decision points."""

from __future__ import annotations

from meridian_contracts import ClassificationResult, Intent, ModelTier
from meridian_orchestrator.routing import route_tier


def _c(intent: Intent, confidence: float, tier: ModelTier) -> ClassificationResult:
    return ClassificationResult(intent=intent, confidence=confidence, model_tier=tier, workflow="t")


def test_refuse_when_confidence_too_low() -> None:
    result = route_tier(_c(Intent.GROUNDED_QA, 0.4, ModelTier.MID), retrieved_doc_count=1)
    assert result is None


def test_high_confidence_keeps_requested_tier() -> None:
    result = route_tier(_c(Intent.GROUNDED_QA, 0.92, ModelTier.MID), retrieved_doc_count=1)
    assert result is ModelTier.MID


def test_mid_confidence_upgrades_one_tier() -> None:
    result = route_tier(_c(Intent.GROUNDED_QA, 0.7, ModelTier.SMALL), retrieved_doc_count=1)
    assert result is ModelTier.MID


def test_mid_confidence_upgrade_caps_at_frontier() -> None:
    result = route_tier(_c(Intent.GROUNDED_QA, 0.7, ModelTier.FRONTIER), retrieved_doc_count=1)
    assert result is ModelTier.FRONTIER


def test_many_retrieved_docs_forces_frontier_for_qa() -> None:
    result = route_tier(_c(Intent.GROUNDED_QA, 0.95, ModelTier.MID), retrieved_doc_count=5)
    assert result is ModelTier.FRONTIER


def test_out_of_scope_always_small() -> None:
    result = route_tier(_c(Intent.OUT_OF_SCOPE, 0.95, ModelTier.MID), retrieved_doc_count=0)
    assert result is ModelTier.SMALL


def test_clarification_always_small() -> None:
    result = route_tier(_c(Intent.CLARIFICATION, 0.7, ModelTier.MID), retrieved_doc_count=2)
    assert result is ModelTier.SMALL
