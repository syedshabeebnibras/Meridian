"""Regressor — orchestrates the end-to-end regression flow.

For each example in a dataset:
  1. Fetch the active prompt template from the registry (or fallback).
  2. Build an AssemblyContext from the example.
  3. Assemble the prompt → ModelRequest.
  4. Call the model client (real or stubbed).
  5. Score the response.
  6. Record the result.

The caller controls whether the registry is consulted (live) or a provided
template is used (offline). This matches the two regression modes in
Section 6.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from meridian_contracts import (
    ModelRequest,
    ModelTier,
    PromptTemplate,
    ResponseFormat,
    RetrievedChunk,
)
from meridian_model_gateway import ModelClient
from meridian_prompt_assembler import (
    AssembledPrompt,
    Assembler,
    AssemblyContext,
)
from pydantic import BaseModel, ConfigDict, Field

from meridian_evaluator.datasets import (
    ClassifierExample,
    Dataset,
    GoldenQAExample,
    load_dataset,
)
from meridian_evaluator.scorers import (
    ClassifierScorer,
    FaithfulnessScorer,
    Scorer,
)

# Maps the template's ModelTier to the LiteLLM alias (Phase 1 config).
TIER_ALIAS = {
    ModelTier.SMALL: "meridian-small",
    ModelTier.MID: "meridian-mid",
    ModelTier.FRONTIER: "meridian-frontier",
}


class RegressionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    prompt_name: str
    prompt_version: int
    total: int
    passed: int
    pass_rate: float
    mean_score: float
    examples: list[dict[str, Any]]


class RegressionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_path: str
    template_name: str
    template_version: int
    scorer: str
    per_example: list[dict[str, Any]] = Field(default_factory=list)


class Regressor:
    """Runs a dataset against a template + client + scorer."""

    def __init__(
        self,
        *,
        template: PromptTemplate,
        client: ModelClient,
        scorer: Scorer,
        assembler: Assembler | None = None,
    ) -> None:
        self._template = template
        self._client = client
        self._scorer = scorer
        self._assembler = assembler or Assembler()

    def run(self, dataset: Dataset, dataset_path: Path | None = None) -> RegressionResult:
        examples = list(dataset.examples)
        scored: list[dict[str, Any]] = []
        for ex in examples:
            if isinstance(ex, ClassifierExample):
                context = AssemblyContext(user_query=ex.input)
                assembled = self._assembler.assemble(self._template, context)
                request = self._to_request(
                    assembled,
                    schema=_CLASSIFIER_SCHEMA,
                    max_tokens=300,
                )
            elif isinstance(ex, GoldenQAExample):
                context = AssemblyContext(
                    user_query=ex.input,
                    retrieved_docs=_to_chunks(ex.retrieved_docs),
                    conversation_history=[],
                    few_shot_examples=[],
                    system_vars=getattr(dataset, "system_vars", {}),
                )
                assembled = self._assembler.assemble(self._template, context)
                request = self._to_request(
                    assembled,
                    schema=_GROUNDED_QA_SCHEMA,
                    max_tokens=1024,
                )
            else:
                raise TypeError(f"unsupported example type: {type(ex)!r}")

            response = self._client.chat(request)
            score = self._scorer.score(ex, response)
            scored.append(
                {
                    "input": ex.input,
                    "passed": score.passed,
                    "score": score.value,
                    "details": score.details,
                }
            )

        total = len(scored)
        passed = sum(1 for s in scored if s["passed"])
        mean = sum(s["score"] for s in scored) / total if total else 0.0
        return RegressionResult(
            dataset_name=dataset.dataset_name,
            prompt_name=self._template.name,
            prompt_version=self._template.version,
            total=total,
            passed=passed,
            pass_rate=(passed / total) if total else 0.0,
            mean_score=mean,
            examples=scored,
        )

    # ------------------------------------------------------------------
    def _to_request(
        self,
        assembled: AssembledPrompt,
        *,
        schema: dict[str, Any] | None,
        max_tokens: int,
    ) -> ModelRequest:
        model_alias = TIER_ALIAS[self._template.model_tier]
        messages = [{"role": m.role, "content": m.content} for m in assembled.messages]
        response_format = None
        if schema is not None:
            response_format = ResponseFormat(
                type="json_schema",
                json_schema={
                    "name": self._template.schema_ref,
                    "strict": True,
                    "schema": schema,
                },
            )
        return ModelRequest.model_validate(
            {
                "model": model_alias,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "response_format": response_format.model_dump(by_alias=True)
                if response_format
                else None,
                "metadata": {
                    "prompt_version": f"{self._template.name}_v{self._template.version}",
                },
            }
        )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------
def _to_chunks(docs: Iterable[Any]) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for i, doc in enumerate(docs, start=1):
        chunks.append(
            RetrievedChunk(
                index=i,
                chunk_id=f"fixture_{i}",
                source_title=doc.title,
                source_url=doc.url,
                content=doc.content,
                relevance_score=doc.relevance,
            )
        )
    return chunks


def make_default_scorer(task_type: str) -> Scorer:
    if task_type == "classifier":
        return ClassifierScorer()
    if task_type == "grounded_qa":
        return FaithfulnessScorer()
    raise ValueError(f"no default scorer for task_type {task_type!r}")


def load_and_run(
    *,
    dataset_path: Path,
    template: PromptTemplate,
    client: ModelClient,
) -> RegressionResult:
    dataset = load_dataset(dataset_path)
    scorer = make_default_scorer(dataset.task_type)
    regressor = Regressor(template=template, client=client, scorer=scorer)
    return regressor.run(dataset, dataset_path=dataset_path)


# ---------------------------------------------------------------------------
# JSON schemas for structured output (mirror the template schema_refs)
# ---------------------------------------------------------------------------
_CLASSIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "confidence": {"type": "number"},
        "model_tier": {"type": "string"},
    },
    "required": ["intent", "confidence", "model_tier"],
}

_GROUNDED_QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_index": {"type": "integer"},
                    "source_title": {"type": "string"},
                    "relevant_excerpt": {"type": "string"},
                },
                "required": ["doc_index", "source_title"],
            },
        },
        "confidence": {"type": "number"},
        "needs_escalation": {"type": "boolean"},
    },
    "required": ["reasoning", "answer", "citations", "confidence", "needs_escalation"],
}
