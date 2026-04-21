"""OutputValidator tests — one test per Section 7 check."""

from __future__ import annotations

from typing import Any

import pytest
from meridian_contracts import ModelResponse, ModelUsage, RetrievedChunk
from meridian_output_validator import OutputValidator, ValidationIssue
from pydantic import HttpUrl


def _response(content: dict[str, Any] | str) -> ModelResponse:
    return ModelResponse(
        id="t",
        model="meridian-mid",
        content=content,
        usage=ModelUsage(input_tokens=0, output_tokens=0),
        latency_ms=10,
    )


def _chunk(index: int, title: str) -> RetrievedChunk:
    return RetrievedChunk(
        index=index,
        chunk_id=f"c{index}",
        source_title=title,
        source_url=HttpUrl("https://example.com/"),
        content="x",
        relevance_score=0.9,
    )


_QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "answer": {"type": "string"},
        "citations": {"type": "array"},
        "confidence": {"type": "number"},
        "needs_escalation": {"type": "boolean"},
    },
    "required": ["answer", "citations", "confidence"],
}


def test_valid_response_with_all_checks_passing() -> None:
    content = {
        "reasoning": "ok",
        "answer": "See [DOC-1] for the procedure.",
        "citations": [{"doc_index": 1, "source_title": "Runbook"}],
        "confidence": 0.9,
        "needs_escalation": False,
    }
    docs = [_chunk(1, "Runbook")]
    result = OutputValidator().validate(_response(content), schema=_QA_SCHEMA, retrieved_docs=docs)
    assert result.valid is True
    assert result.issues == []


def test_schema_mismatch_flags_error() -> None:
    content = {"answer": "ok"}  # missing required citations + confidence
    result = OutputValidator().validate(_response(content), schema=_QA_SCHEMA)
    assert result.valid is False
    codes = {i.code for i in result.issues}
    assert "schema_mismatch" in codes


def test_missing_citation_reference_in_answer() -> None:
    content = {
        "answer": "Refer to [DOC-2] for details.",
        "citations": [{"doc_index": 1, "source_title": "Runbook"}],
        "confidence": 0.9,
        "needs_escalation": False,
    }
    docs = [_chunk(1, "Runbook")]  # DOC-2 wasn't retrieved
    result = OutputValidator().validate(_response(content), retrieved_docs=docs)
    assert result.valid is False
    codes = {i.code for i in result.issues}
    assert "missing_citation" in codes


def test_hallucinated_citation_title_is_error() -> None:
    content = {
        "answer": "See [DOC-1].",
        "citations": [
            {"doc_index": 1, "source_title": "Real Runbook"},
            {"doc_index": 2, "source_title": "Fabricated Runbook"},
        ],
        "confidence": 0.9,
        "needs_escalation": False,
    }
    docs = [_chunk(1, "Real Runbook")]
    result = OutputValidator().validate(_response(content), retrieved_docs=docs)
    codes = {i.code for i in result.issues}
    assert "citation_hallucination" in codes
    assert result.valid is False


def test_unjustified_answer_flagged_when_confidence_low() -> None:
    content = {
        "answer": "The SLA is 99.99%.",
        "citations": [],
        "confidence": 0.3,
        "needs_escalation": False,
    }
    result = OutputValidator().validate(_response(content))
    codes = {i.code for i in result.issues}
    assert "unjustified_answer" in codes


def test_low_confidence_with_refusal_passes() -> None:
    content = {
        "answer": "I don't have enough information to answer this reliably.",
        "citations": [],
        "confidence": 0.3,
        "needs_escalation": False,
    }
    result = OutputValidator().validate(_response(content))
    # No unjustified_answer issue because the answer *is* a refusal.
    codes = {i.code for i in result.issues}
    assert "unjustified_answer" not in codes


def test_too_long_answer_is_warning_not_error() -> None:
    content = {
        "answer": "x" * 100,
        "citations": [],
        "confidence": 0.9,
        "needs_escalation": False,
    }
    result = OutputValidator(max_answer_chars=50).validate(_response(content))
    assert result.valid is True  # warning doesn't fail validation
    assert any(i.code == "too_long" and i.severity == "warning" for i in result.issues)


def test_string_content_with_schema_fails() -> None:
    result = OutputValidator().validate(_response("freeform text"), schema=_QA_SCHEMA)
    assert result.valid is False
    assert result.issues[0].code == "schema_mismatch"


def test_no_schema_and_no_retrieved_docs_still_runs_refusal_and_length() -> None:
    content = {"answer": "hi", "confidence": 0.9, "citations": []}
    result = OutputValidator().validate(_response(content))
    assert result.valid is True


def test_citations_not_a_list_is_format_error() -> None:
    content = {"answer": "hi", "confidence": 0.9, "citations": "not a list"}
    result = OutputValidator().validate(_response(content))
    assert result.valid is False
    assert any(i.code == "format_error" for i in result.issues)


@pytest.mark.parametrize(
    "issue",
    [
        ValidationIssue(code="schema_mismatch", message="x", severity="error"),
        ValidationIssue(code="too_long", message="x", severity="warning"),
    ],
)
def test_validation_issue_is_pydantic_strict(issue: ValidationIssue) -> None:
    assert issue.model_dump()["severity"] in {"error", "warning"}
