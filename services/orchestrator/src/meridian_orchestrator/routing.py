"""Model routing — Section 7 §Model routing logic.

Rules:
- confidence < 0.6  → refuse (return None)
- 0.6 ≤ confidence < 0.85 → upgrade one tier
- confidence ≥ 0.85 → use the tier the classifier asked for
- intent == grounded_qa with >3 retrieved docs → force frontier
- intent == out_of_scope / clarification → force small
"""

from __future__ import annotations

from meridian_contracts import ClassificationResult, Intent, ModelTier

# Ordered from cheapest to most capable so "upgrade" is a simple index lookup.
_TIER_LADDER: tuple[ModelTier, ...] = (
    ModelTier.SMALL,
    ModelTier.MID,
    ModelTier.FRONTIER,
)


def route_tier(
    classification: ClassificationResult,
    *,
    retrieved_doc_count: int,
    refusal_threshold: float = 0.6,
    upgrade_threshold: float = 0.85,
) -> ModelTier | None:
    """Return the tier to dispatch on, or None to refuse.

    `retrieved_doc_count` is checked only for grounded_qa — multi-doc
    synthesis gets promoted to frontier per Section 7.
    """
    if classification.confidence < refusal_threshold:
        return None

    intent = classification.intent
    if intent in (Intent.OUT_OF_SCOPE, Intent.CLARIFICATION):
        return ModelTier.SMALL

    base = classification.model_tier
    if classification.confidence < upgrade_threshold:
        base = _bump(base)

    if intent is Intent.GROUNDED_QA and retrieved_doc_count > 3:
        base = ModelTier.FRONTIER

    return base


def _bump(tier: ModelTier) -> ModelTier:
    idx = _TIER_LADDER.index(tier)
    return _TIER_LADDER[min(idx + 1, len(_TIER_LADDER) - 1)]
