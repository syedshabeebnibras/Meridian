"""Round-trip tests against the exact example payloads from Section 8.

Every model in `meridian_contracts` must accept the example JSON from the
execution plan and re-serialise it without data loss. These tests are the
contract guardrail: if Section 8 changes, these tests should change, and
vice versa.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from meridian_contracts import (
    EvaluationRecord,
    ModelRequest,
    ModelResponse,
    OrchestrationState,
    PromptTemplate,
    RetrievalResult,
    TelemetryEvent,
    ToolInvocation,
    ToolResult,
    UserRequest,
)
from pydantic import ValidationError


def _roundtrip(cls: Any, payload: dict[str, Any]) -> None:
    """Parse, serialise, parse again — confirm structural stability."""
    instance = cls.model_validate(payload)
    serialised = json.loads(instance.model_dump_json(by_alias=True, exclude_none=False))
    reparsed = cls.model_validate(serialised)
    assert instance == reparsed


# ---- Section 8: User request --------------------------------------------------
USER_REQUEST: dict[str, Any] = {
    "request_id": "req_a1b2c3d4e5f6",
    "user_id": "user_alice_eng",
    "session_id": "sess_x7y8z9",
    "query": "What is the escalation procedure for a P1 database outage?",
    "conversation_history": [
        {
            "role": "user",
            "content": "Tell me about incident response procedures",
            "timestamp": "2026-04-16T10:00:00Z",
        },
        {
            "role": "assistant",
            "content": "We have procedures for P1 through P4...",
            "timestamp": "2026-04-16T10:00:05Z",
        },
    ],
    "metadata": {
        "source": "web_ui",
        "user_department": "engineering",
        "timestamp": "2026-04-16T10:00:30Z",
    },
}


def test_user_request_matches_section_8() -> None:
    _roundtrip(UserRequest, USER_REQUEST)


# ---- Section 8: Orchestration state -------------------------------------------
ORCHESTRATION_STATE: dict[str, Any] = {
    "request_id": "req_a1b2c3d4e5f6",
    "current_state": "DISPATCHED",
    "classification": {
        "intent": "grounded_qa",
        "confidence": 0.92,
        "model_tier": "mid",
        "workflow": "grounded_qa_v3",
    },
    "retrieval": {
        "query_rewritten": "P1 database outage escalation procedure",
        "chunks_retrieved": 5,
        "chunks_after_rerank": 3,
        "top_relevance_score": 0.94,
    },
    "prompt": {
        "template_name": "grounded_qa",
        "template_version": 3,
        "total_tokens_assembled": 4820,
        "cache_prefix_tokens": 1200,
    },
    "dispatch": {
        "model": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "attempt": 1,
        "idempotency_key": "req_a1b2c3d4e5f6_attempt_1",
    },
    "timings_ms": {
        "input_guardrails": 45,
        "classification": 280,
        "retrieval": 340,
        "assembly": 12,
        "dispatch_pending": None,
        "validation": None,
        "output_guardrails": None,
        "total": None,
    },
    "errors": [],
}


def test_orchestration_state_matches_section_8() -> None:
    _roundtrip(OrchestrationState, ORCHESTRATION_STATE)


# ---- Section 8: Prompt template -----------------------------------------------
PROMPT_TEMPLATE: dict[str, Any] = {
    "name": "grounded_qa",
    "version": 3,
    "model_tier": "mid",
    "min_model": "claude-sonnet-4-20250514",
    "template": (
        "[SYSTEM] You are Meridian, an internal knowledge assistant...\n\n"
        "[RETRIEVED DOCUMENTS]\n{{ retrieved_docs }}\n\n"
        "[USER] {{ user_query }}"
    ),
    "parameters": ["company_name", "retrieved_docs", "conversation_history", "user_query"],
    "schema_ref": "grounded_qa_response_v2",
    "few_shot_dataset": "grounded_qa_examples_v1",
    "token_budget": {
        "system": 500,
        "few_shot": 800,
        "retrieval": 6000,
        "history": 2000,
        "query": 500,
        "total_max": 16000,
    },
    "cache_control": {
        "breakpoints": ["after_system", "after_few_shot"],
        "prefix_stable": True,
    },
    "activation": {
        "environment": "production",
        "status": "active",
        "canary_percentage": 0,
        "activated_at": "2026-04-14T09:00:00Z",
        "activated_by": "alice@company.com",
    },
    "eval_results": {
        "regression_pass_rate": 0.94,
        "faithfulness_score": 0.91,
        "avg_latency_ms": 2800,
    },
}


def test_prompt_template_matches_section_8() -> None:
    _roundtrip(PromptTemplate, PROMPT_TEMPLATE)


# ---- Section 8: Model request -------------------------------------------------
MODEL_REQUEST: dict[str, Any] = {
    "model": "claude-sonnet-4-20250514",
    "messages": [
        {"role": "system", "content": "You are Meridian, an internal knowledge assistant..."},
        {
            "role": "user",
            "content": (
                "[RETRIEVED DOCUMENTS]\n[DOC-1] Source: Incident Response Runbook...\n\n"
                "[USER] What is the escalation procedure for a P1 database outage?"
            ),
        },
    ],
    "max_tokens": 1024,
    "temperature": 0.1,
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "grounded_qa_response",
            "strict": True,
            "schema": {
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
                "required": [
                    "reasoning",
                    "answer",
                    "citations",
                    "confidence",
                    "needs_escalation",
                ],
            },
        },
    },
    "metadata": {
        "request_id": "req_a1b2c3d4e5f6",
        "prompt_version": "grounded_qa_v3",
        "idempotency_key": "req_a1b2c3d4e5f6_attempt_1",
    },
}


def test_model_request_matches_section_8() -> None:
    _roundtrip(ModelRequest, MODEL_REQUEST)


# ---- Section 8: Model response ------------------------------------------------
MODEL_RESPONSE: dict[str, Any] = {
    "id": "msg_abc123",
    "model": "claude-sonnet-4-20250514",
    "content": {
        "reasoning": "The user is asking about P1 database outage escalation...",
        "answer": "For a P1 database outage, the escalation procedure is: ...",
        "citations": [
            {
                "doc_index": 1,
                "source_title": "Incident Response Runbook v4.2",
                "relevant_excerpt": "P1 incidents require immediate PagerDuty escalation...",
            },
            {
                "doc_index": 2,
                "source_title": "On-Call Procedures 2026",
                "relevant_excerpt": "Status updates must be posted every 15 minutes...",
            },
        ],
        "confidence": 0.93,
        "needs_escalation": False,
    },
    "usage": {
        "input_tokens": 4820,
        "output_tokens": 312,
        "cache_read_input_tokens": 1200,
        "cache_creation_input_tokens": 0,
    },
    "latency_ms": 2340,
}


def test_model_response_matches_section_8() -> None:
    _roundtrip(ModelResponse, MODEL_RESPONSE)


# ---- Section 8: Tool invocation -----------------------------------------------
TOOL_INVOCATION: dict[str, Any] = {
    "tool_call_id": "tc_001",
    "tool_name": "jira_create_ticket",
    "parameters": {
        "project": "ENG",
        "issue_type": "bug",
        "title": "Auth service memory leak in session handler",
        "description": (
            "Memory leak detected in the session handler component of the auth service, "
            "causing OOM kills after ~48 hours of operation."
        ),
        "priority": "high",
        "component": "auth-service",
        "labels": ["memory-leak", "meridian-created"],
    },
    "requires_confirmation": True,
    "confirmation_message": (
        "I'll create a High-priority bug ticket in the ENG project titled "
        "'Auth service memory leak in session handler'. Should I proceed?"
    ),
    "validation": {
        "schema_valid": True,
        "parameters_allowlisted": True,
        "no_injection_detected": True,
    },
}


def test_tool_invocation_matches_section_8() -> None:
    _roundtrip(ToolInvocation, TOOL_INVOCATION)


# ---- Section 8: Tool result ---------------------------------------------------
TOOL_RESULT: dict[str, Any] = {
    "tool_call_id": "tc_001",
    "tool_name": "jira_create_ticket",
    "status": "success",
    "result": {
        "ticket_id": "ENG-4521",
        "ticket_url": "https://company.atlassian.net/browse/ENG-4521",
        "created_at": "2026-04-16T10:01:00Z",
    },
    "execution_time_ms": 1200,
}


def test_tool_result_matches_section_8() -> None:
    _roundtrip(ToolResult, TOOL_RESULT)


# ---- Section 8: Retrieval result ----------------------------------------------
RETRIEVAL_RESULT: dict[str, Any] = {
    "query": "P1 database outage escalation procedure",
    "query_rewritten": "escalation procedure P1 database outage incident response",
    "results": [
        {
            "index": 1,
            "chunk_id": "chunk_ir_runbook_042",
            "source_title": "Incident Response Runbook v4.2",
            "source_url": "https://confluence.company.com/ir-runbook",
            "content": (
                "P1 incidents require immediate PagerDuty escalation to the on-call database SRE..."
            ),
            "relevance_score": 0.94,
            "rerank_score": 0.97,
            "metadata": {
                "last_updated": "2026-03-15",
                "author": "sre-team",
                "document_type": "runbook",
            },
        }
    ],
    "total_chunks_retrieved": 12,
    "total_after_rerank": 3,
    "retrieval_latency_ms": 340,
}


def test_retrieval_result_matches_section_8() -> None:
    _roundtrip(RetrievalResult, RETRIEVAL_RESULT)


# ---- Section 8: Evaluation record ---------------------------------------------
EVALUATION_RECORD: dict[str, Any] = {
    "eval_id": "eval_20260416_001",
    "request_id": "req_a1b2c3d4e5f6",
    "eval_type": "online_sample",
    "scores": {
        "faithfulness": 0.95,
        "relevance": 0.88,
        "citation_accuracy": 1.0,
        "response_completeness": 0.85,
        "safety_pass": True,
    },
    "judge_model": "claude-sonnet-4-20250514",
    "judge_prompt_version": "faithfulness_judge_v2",
    "golden_answer": None,
    "human_label": None,
    "timestamp": "2026-04-16T10:01:05Z",
    "prompt_version": "grounded_qa_v3",
    "model_used": "claude-sonnet-4-20250514",
    "latency_ms": 2340,
    "total_cost_usd": 0.012,
}


def test_evaluation_record_matches_section_8() -> None:
    _roundtrip(EvaluationRecord, EVALUATION_RECORD)


# ---- Section 8: Telemetry event -----------------------------------------------
TELEMETRY_EVENT: dict[str, Any] = {
    "trace_id": "tr_a1b2c3d4e5f6",
    "span_id": "sp_model_dispatch",
    "parent_span_id": "sp_orchestration",
    "service": "meridian-orchestrator",
    "operation": "model_dispatch",
    "timestamp": "2026-04-16T10:00:32Z",
    "duration_ms": 2340,
    "attributes": {
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": "claude-sonnet-4-20250514",
        "gen_ai.response.model": "claude-sonnet-4-20250514",
        "gen_ai.usage.input_tokens": 4820,
        "gen_ai.usage.output_tokens": 312,
        "gen_ai.usage.cache_read_tokens": 1200,
        "gen_ai.response.finish_reason": "end_turn",
        "meridian.request_id": "req_a1b2c3d4e5f6",
        "meridian.prompt_version": "grounded_qa_v3",
        "meridian.model_tier": "mid",
        "meridian.intent": "grounded_qa",
        "meridian.cost_usd": 0.012,
        "meridian.cache_hit": "prefix_partial",
        "meridian.provider_attempt": 1,
        "meridian.retrieval_chunks_used": 3,
    },
    "status": "ok",
}


def test_telemetry_event_matches_section_8() -> None:
    _roundtrip(TelemetryEvent, TELEMETRY_EVENT)


# ---- Strictness guard: every contract forbids extra fields --------------------
@pytest.mark.parametrize(
    ("cls", "example"),
    [
        (UserRequest, USER_REQUEST),
        (OrchestrationState, ORCHESTRATION_STATE),
        (PromptTemplate, PROMPT_TEMPLATE),
        (ModelRequest, MODEL_REQUEST),
        (ModelResponse, MODEL_RESPONSE),
        (ToolInvocation, TOOL_INVOCATION),
        (ToolResult, TOOL_RESULT),
        (RetrievalResult, RETRIEVAL_RESULT),
        (EvaluationRecord, EVALUATION_RECORD),
        (TelemetryEvent, TELEMETRY_EVENT),
    ],
)
def test_contracts_forbid_extra_fields(cls: Any, example: dict[str, Any]) -> None:
    bad = {**example, "__unexpected__": "surprise"}
    with pytest.raises(ValidationError):
        cls.model_validate(bad)
