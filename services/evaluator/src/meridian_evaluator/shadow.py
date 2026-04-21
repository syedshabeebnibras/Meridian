"""Shadow testing — run the same request through two Orchestrator configs
and compare the results with a PairwiseJudge.

Section 10 §Shadow testing:
  1. Deploy new version in shadow mode (0% traffic)
  2. Process 500+ requests through both old and new version
  3. Compare eval scores — pairwise on quality, absolute on latency/cost
  4. New version must be non-regressing on >= 95% of cases
  5. Only then promote to canary (5%)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from meridian_contracts import UserRequest
from pydantic import BaseModel, ConfigDict, Field

from meridian_evaluator.judges import PairwiseJudge, PairwiseResult


class ShadowTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    answer_a: str
    answer_b: str
    latency_ms_a: int
    latency_ms_b: int
    pairwise: PairwiseResult


class ShadowReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    wins_a: int
    wins_b: int
    ties: int
    avg_latency_ms_a: float
    avg_latency_ms_b: float
    trials: list[ShadowTrial] = Field(default_factory=list)

    @property
    def non_regression_rate(self) -> float:
        """Share of trials where B (new) is not worse than A (old)."""
        if self.total == 0:
            return 1.0
        return (self.wins_b + self.ties) / self.total

    @property
    def passes_95_gate(self) -> bool:
        return self.non_regression_rate >= 0.95


@dataclass
class ShadowRunner:
    """Runs two orchestrator configs side-by-side over the same inputs.

    `orchestrator_a` is the control (current production), `orchestrator_b`
    is the candidate. The judge scores each trial pairwise.
    """

    orchestrator_a: Any  # anything with .handle(UserRequest) -> OrchestratorReply
    orchestrator_b: Any
    judge: PairwiseJudge
    extract_answer: Any = field(default=None)

    def run(self, queries: Iterable[UserRequest]) -> ShadowReport:
        trials: list[ShadowTrial] = []
        total_latency_a = 0
        total_latency_b = 0
        wins_a = wins_b = ties = 0

        for query in queries:
            reply_a = self.orchestrator_a.handle(query)
            reply_b = self.orchestrator_b.handle(query)

            answer_a = _answer_from_reply(reply_a, self.extract_answer)
            answer_b = _answer_from_reply(reply_b, self.extract_answer)

            pairwise = self.judge.score(
                question=query.query,
                answer_a=answer_a,
                answer_b=answer_b,
            )
            latency_a = reply_a.orchestration_state.timings_ms.total or 0
            latency_b = reply_b.orchestration_state.timings_ms.total or 0
            total_latency_a += latency_a
            total_latency_b += latency_b

            if pairwise.winner == "A":
                wins_a += 1
            elif pairwise.winner == "B":
                wins_b += 1
            else:
                ties += 1

            trials.append(
                ShadowTrial(
                    query=query.query,
                    answer_a=answer_a,
                    answer_b=answer_b,
                    latency_ms_a=latency_a,
                    latency_ms_b=latency_b,
                    pairwise=pairwise,
                )
            )

        total = len(trials)
        return ShadowReport(
            total=total,
            wins_a=wins_a,
            wins_b=wins_b,
            ties=ties,
            avg_latency_ms_a=(total_latency_a / total) if total else 0.0,
            avg_latency_ms_b=(total_latency_b / total) if total else 0.0,
            trials=trials,
        )


def _answer_from_reply(reply: Any, extractor: Any) -> str:
    """Pull the answer text out of an OrchestratorReply. Defaults to the
    model_response.content.answer field; a custom extractor can override."""
    if extractor is not None:
        return str(extractor(reply))
    if reply.model_response is None:
        return reply.error_message or ""
    content = reply.model_response.content
    if isinstance(content, dict):
        return str(content.get("answer", ""))
    return str(content)
