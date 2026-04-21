"""ThresholdingClient — drops chunks below a minimum relevance score.

Wraps any RetrievalClient. Section 7 §Confidence checks: low-confidence
retrieval should trigger refusal at the orchestrator level. This wrapper
hands the orchestrator a `RetrievalResult` whose `results` list is
post-filtered, so a count of zero is the signal to refuse.
"""

from __future__ import annotations

from dataclasses import dataclass

from meridian_contracts import RetrievalResult

from meridian_retrieval_client.protocols import RetrievalClient


@dataclass
class ThresholdingClient:
    inner: RetrievalClient
    min_relevance: float = 0.5

    def retrieve(self, query: str, *, top_k: int = 10) -> RetrievalResult:
        raw = self.inner.retrieve(query, top_k=top_k)
        kept = [c for c in raw.results if c.relevance_score >= self.min_relevance]
        return raw.model_copy(
            update={
                "results": kept,
                "total_after_rerank": len(kept),
            }
        )
