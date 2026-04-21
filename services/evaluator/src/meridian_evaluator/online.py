"""Online eval sampler — Section 10.

  - 10% of production traffic sampled randomly
  - Each sample scored on: faithfulness, relevance
  - Scores aggregated per segment (intent, prompt version, tier)
  - Alerting when any segment drops below 0.8 (Section 10)

Phase 5 ships the sampling + scoring layer. Writing to the eval_results
table (and wiring into the Langfuse trace stream) is Phase 6/7. The
sampler is pure — callers plug it into whichever transport they want.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from meridian_contracts import EvaluationRecord, EvaluationScores, EvaluationType
from pydantic import BaseModel, ConfigDict

from meridian_evaluator.judges import FaithfulnessJudge, RelevanceJudge


class SampleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sampled: bool
    reason: str


@dataclass
class OnlineEvalSampler:
    """Picks 10% of requests and scores them with the configured judges.

    Usage:
        sampler = OnlineEvalSampler(
            faithfulness=FaithfulnessJudge(client=resilient_client()),
            relevance=RelevanceJudge(client=resilient_client()),
        )
        decision = sampler.should_sample()
        if decision.sampled:
            record = sampler.score(
                request_id=request.request_id,
                question=request.query,
                answer=reply.model_response.content["answer"],
                retrieved_docs_text=...,
                prompt_version="grounded_qa_v3",
                model_used="meridian-mid",
                latency_ms=reply.orchestration_state.timings_ms.total,
                total_cost_usd=0.012,
            )
            # write `record` to eval_results (Phase 6/7).
    """

    faithfulness: FaithfulnessJudge | None = None
    relevance: RelevanceJudge | None = None
    sample_rate: float = 0.10
    rng: random.Random = field(default_factory=random.Random)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))

    def should_sample(self) -> SampleDecision:
        roll = self.rng.random()
        if roll < self.sample_rate:
            return SampleDecision(sampled=True, reason=f"rng={roll:.4f}<{self.sample_rate:.4f}")
        return SampleDecision(sampled=False, reason=f"rng={roll:.4f}>={self.sample_rate:.4f}")

    def score(
        self,
        *,
        request_id: str,
        question: str,
        answer: str,
        retrieved_docs_text: str,
        prompt_version: str,
        model_used: str,
        latency_ms: int,
        total_cost_usd: float,
        extras: dict[str, Any] | None = None,
    ) -> EvaluationRecord:
        """Build an EvaluationRecord for this sample."""
        scores = EvaluationScores()

        if self.faithfulness is not None:
            f = self.faithfulness.score(answer=answer, retrieved_docs_text=retrieved_docs_text)
            scores = scores.model_copy(update={"faithfulness": f.value})
        if self.relevance is not None:
            r = self.relevance.score(question=question, answer=answer)
            scores = scores.model_copy(update={"relevance": r.value})

        # Which judge model actually ran? Prefer faithfulness since it's the
        # Section-10 gate metric; fall back to relevance.
        judge_model = "meridian-mid"  # Both judges default to mid; template records the alias
        judge_prompt_version = "faithfulness_judge_v1"

        return EvaluationRecord(
            eval_id=f"eval_online_{uuid.uuid4().hex[:12]}",
            request_id=request_id,
            eval_type=EvaluationType.ONLINE_SAMPLE,
            scores=scores,
            judge_model=judge_model,
            judge_prompt_version=judge_prompt_version,
            golden_answer=None,
            human_label=None,
            timestamp=self.clock(),
            prompt_version=prompt_version,
            model_used=model_used,
            latency_ms=latency_ms,
            total_cost_usd=total_cost_usd,
        )
