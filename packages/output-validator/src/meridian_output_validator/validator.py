"""OutputValidator — Section 7 §Output validation.

Checks, in order:

  1. Schema check       — `content` matches the declared JSON schema.
  2. Citation check     — every [DOC-N] reference points to a retrieved chunk,
                          and every `citations[].source_title` is in retrieved.
  3. Refusal check      — low-confidence responses must be explicit refusals,
                          not fabricated answers.
  4. Length check       — answer text is within min/max bounds.
  5. Format check       — citation list is well-formed (list of dicts).

Each issue carries a severity — `error` fails the overall result; `warning`
records a concern but keeps `valid=True`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Literal

from jsonschema import Draft202012Validator
from meridian_contracts import ModelResponse, RetrievedChunk
from pydantic import BaseModel, ConfigDict, Field

_DOC_REF_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[DOC-(\d+)\]")
_REFUSAL_HINT: Final[str] = "i don't have enough information"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    severity: Literal["error", "warning"]


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)

    @classmethod
    def _from_issues(cls, issues: list[ValidationIssue]) -> ValidationResult:
        has_error = any(i.severity == "error" for i in issues)
        return cls(valid=not has_error, issues=issues)


@dataclass
class OutputValidator:
    """Stateless validator. Configure per-template via constructor args."""

    min_answer_chars: int = 1
    max_answer_chars: int = 4000
    refusal_confidence_threshold: float = 0.6

    def validate(
        self,
        response: ModelResponse,
        *,
        schema: dict[str, Any] | None = None,
        retrieved_docs: list[RetrievedChunk] | None = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        content = response.content

        if schema is not None:
            issues.extend(self._check_schema(content, schema))

        if isinstance(content, dict):
            issues.extend(self._check_citations(content, retrieved_docs or []))
            issues.extend(self._check_refusal(content))
            issues.extend(self._check_length(content))
        else:
            # Free-text response — we can't do any dict-shaped checks.
            issues.append(
                ValidationIssue(
                    code="non_structured_content",
                    message="content is not a dict; skipping dict-shaped checks",
                    severity="warning",
                )
            )

        return ValidationResult._from_issues(issues)

    # ------------------------------------------------------------------
    # individual checks
    # ------------------------------------------------------------------
    def _check_schema(
        self, content: dict[str, Any] | str, schema: dict[str, Any]
    ) -> list[ValidationIssue]:
        if isinstance(content, str):
            return [
                ValidationIssue(
                    code="schema_mismatch",
                    message="expected dict content, got string",
                    severity="error",
                )
            ]
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(content), key=lambda e: list(e.path))
        return [
            ValidationIssue(
                code="schema_mismatch",
                message=f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}",
                severity="error",
            )
            for err in errors
        ]

    def _check_citations(
        self, content: dict[str, Any], retrieved_docs: list[RetrievedChunk]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        answer = str(content.get("answer", ""))
        citations_raw = content.get("citations", [])

        # Normalize citations into a list of dicts.
        if not isinstance(citations_raw, list):
            issues.append(
                ValidationIssue(
                    code="format_error",
                    message="citations must be a list",
                    severity="error",
                )
            )
            return issues

        # [DOC-N] in answer text → must have a corresponding retrieved doc.
        referenced_indices = {int(m.group(1)) for m in _DOC_REF_PATTERN.finditer(answer)}
        retrieved_indices = {d.index for d in retrieved_docs}
        for idx in sorted(referenced_indices - retrieved_indices):
            issues.append(
                ValidationIssue(
                    code="missing_citation",
                    message=f"answer cites [DOC-{idx}] but no such retrieved doc",
                    severity="error",
                )
            )

        # citations[].source_title → must be a retrieved doc (hallucination check).
        retrieved_titles = {d.source_title for d in retrieved_docs}
        for c in citations_raw:
            if not isinstance(c, dict):
                continue
            title = c.get("source_title")
            if title and retrieved_docs and title not in retrieved_titles:
                issues.append(
                    ValidationIssue(
                        code="citation_hallucination",
                        message=f"citation {title!r} was not in the retrieved set",
                        severity="error",
                    )
                )

        return issues

    def _check_refusal(self, content: dict[str, Any]) -> list[ValidationIssue]:
        confidence = content.get("confidence")
        answer = str(content.get("answer", ""))
        if not isinstance(confidence, (int, float)):
            return []
        if confidence < self.refusal_confidence_threshold and _REFUSAL_HINT not in answer.lower():
            return [
                ValidationIssue(
                    code="unjustified_answer",
                    message=(
                        f"confidence={confidence:.2f} is below threshold "
                        f"{self.refusal_confidence_threshold:.2f} but the answer is not a refusal"
                    ),
                    severity="error",
                )
            ]
        return []

    def _check_length(self, content: dict[str, Any]) -> list[ValidationIssue]:
        answer = str(content.get("answer", ""))
        if len(answer) < self.min_answer_chars:
            return [
                ValidationIssue(
                    code="too_short",
                    message=f"answer is {len(answer)} chars; expected ≥{self.min_answer_chars}",
                    severity="error",
                )
            ]
        if len(answer) > self.max_answer_chars:
            return [
                ValidationIssue(
                    code="too_long",
                    message=f"answer is {len(answer)} chars; expected ≤{self.max_answer_chars}",
                    severity="warning",
                )
            ]
        return []
