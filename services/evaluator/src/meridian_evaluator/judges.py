"""LLM-as-judge — Section 10 rubrics.

Each judge is a thin wrapper around a ModelClient that renders a rubric
prompt, calls the model, and parses a scored response. Tests can use
StubModelClient; live runs use LiteLLMClient (or whatever resilient stack
is injected).

Rubrics live in prompts/judge_*/v1.yaml so they're subject to the same
versioning + rollback machinery as any other production prompt.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelRequest,
    ModelResponse,
    ModelTier,
    PromptTemplate,
    ResponseFormat,
    TokenBudget,
)
from meridian_model_gateway import ModelClient
from meridian_prompt_assembler import Assembler, AssemblyContext
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[4]

_TIER_ALIAS = {
    ModelTier.SMALL: "meridian-small",
    ModelTier.MID: "meridian-mid",
    ModelTier.FRONTIER: "meridian-frontier",
}

# Strict-mode JSON schemas — additionalProperties:false at every object level
# and every property listed in `required`.
_SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
    "required": ["score", "reasoning"],
}

_PAIRWISE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "tie"]},
        "reasoning": {"type": "string"},
    },
    "required": ["winner", "reasoning"],
}


class JudgeScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric: str
    value: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class PairwiseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    winner: Literal["A", "B", "tie"]
    reasoning: str = ""


def _load_template(name: str) -> PromptTemplate:
    """Load a judge template by name from prompts/<name>/v1.yaml.

    Keeps the judges self-contained — no DB round-trip needed to run them.
    """
    from datetime import UTC, datetime

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
            environment="judge",
            status=ActivationStatus.DRAFT,
            canary_percentage=0,
            activated_at=datetime.now(tz=UTC),
            activated_by="judge@meridian.example",
        ),
    )


def _parse_json_content(response: ModelResponse) -> dict[str, Any]:
    content = response.content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return content if isinstance(content, dict) else {}


@dataclass
class FaithfulnessJudge:
    """Scores an answer's faithfulness to the retrieved documents (Section 10 rubric)."""

    client: ModelClient
    template_name: str = "judge_faithfulness"
    assembler: Assembler | None = None

    def score(self, *, answer: str, retrieved_docs_text: str) -> JudgeScore:
        template = _load_template(self.template_name)
        assembler = self.assembler or Assembler()
        assembled = assembler.assemble(
            template,
            AssemblyContext(
                user_query="",  # not used — the template reads answer + retrieved_docs_text
                system_vars={
                    "answer": answer,
                    "retrieved_docs_text": retrieved_docs_text,
                },
            ),
        )
        request = ModelRequest(
            model=_TIER_ALIAS[template.model_tier],
            messages=[{"role": m.role, "content": m.content} for m in assembled.messages],
            max_tokens=400,
            temperature=0.0,
            response_format=ResponseFormat(
                type="json_schema",
                json_schema={
                    "name": template.schema_ref,
                    "strict": True,
                    "schema": _SCORE_SCHEMA,
                },
            ),
        )
        parsed = _parse_json_content(self.client.chat(request))
        return JudgeScore(
            rubric="faithfulness",
            value=float(parsed.get("score", 0.0)),
            reasoning=str(parsed.get("reasoning", "")),
        )


@dataclass
class RelevanceJudge:
    """Scores how directly an answer addresses the question (Section 10 rubric)."""

    client: ModelClient
    template_name: str = "judge_relevance"
    assembler: Assembler | None = None

    def score(self, *, question: str, answer: str) -> JudgeScore:
        template = _load_template(self.template_name)
        assembler = self.assembler or Assembler()
        assembled = assembler.assemble(
            template,
            AssemblyContext(
                user_query="",
                system_vars={"question": question, "answer": answer},
            ),
        )
        request = ModelRequest(
            model=_TIER_ALIAS[template.model_tier],
            messages=[{"role": m.role, "content": m.content} for m in assembled.messages],
            max_tokens=300,
            temperature=0.0,
            response_format=ResponseFormat(
                type="json_schema",
                json_schema={
                    "name": template.schema_ref,
                    "strict": True,
                    "schema": _SCORE_SCHEMA,
                },
            ),
        )
        parsed = _parse_json_content(self.client.chat(request))
        return JudgeScore(
            rubric="relevance",
            value=float(parsed.get("score", 0.0)),
            reasoning=str(parsed.get("reasoning", "")),
        )


@dataclass
class PairwiseJudge:
    """A/B comparison — more reliable than absolute scoring (Section 10)."""

    client: ModelClient
    template_name: str = "judge_pairwise"
    assembler: Assembler | None = None

    def score(
        self,
        *,
        question: str,
        answer_a: str,
        answer_b: str,
        retrieved_docs_text: str = "",
    ) -> PairwiseResult:
        template = _load_template(self.template_name)
        assembler = self.assembler or Assembler()
        assembled = assembler.assemble(
            template,
            AssemblyContext(
                user_query="",
                system_vars={
                    "question": question,
                    "answer_a": answer_a,
                    "answer_b": answer_b,
                    "retrieved_docs_text": retrieved_docs_text,
                },
            ),
        )
        request = ModelRequest(
            model=_TIER_ALIAS[template.model_tier],
            messages=[{"role": m.role, "content": m.content} for m in assembled.messages],
            max_tokens=400,
            temperature=0.0,
            response_format=ResponseFormat(
                type="json_schema",
                json_schema={
                    "name": template.schema_ref,
                    "strict": True,
                    "schema": _PAIRWISE_SCHEMA,
                },
            ),
        )
        parsed = _parse_json_content(self.client.chat(request))
        winner = parsed.get("winner", "tie")
        if winner not in ("A", "B", "tie"):
            winner = "tie"
        return PairwiseResult(
            winner=winner,
            reasoning=str(parsed.get("reasoning", "")),
        )


# ---------------------------------------------------------------------------
# Cohen's kappa — Section 10 calibration gate
# ---------------------------------------------------------------------------
def cohens_kappa(
    judge_scores: Iterable[float],
    human_scores: Iterable[float],
    *,
    buckets: int = 4,
) -> float:
    """Compute Cohen's kappa between continuous 0-1 scores by bucketing.

    Default buckets of 4 map the 0.0/0.25/0.5/0.75/1.0 rubric levels to
    ordinal categories. Returns a value in [-1, 1]; > 0.6 is the Section 10
    calibration gate.
    """
    j = list(judge_scores)
    h = list(human_scores)
    if not j or len(j) != len(h):
        raise ValueError("judge_scores and human_scores must be non-empty and equal length")

    def _bucket(x: float) -> int:
        x = max(0.0, min(1.0, x))
        return min(int(x * buckets), buckets - 1)

    j_cat = [_bucket(x) for x in j]
    h_cat = [_bucket(x) for x in h]
    n = len(j_cat)
    agree = sum(1 for a, b in zip(j_cat, h_cat, strict=True) if a == b)
    p_o = agree / n

    j_counts = [j_cat.count(k) for k in range(buckets)]
    h_counts = [h_cat.count(k) for k in range(buckets)]
    p_e = sum((j_counts[k] / n) * (h_counts[k] / n) for k in range(buckets))
    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)
