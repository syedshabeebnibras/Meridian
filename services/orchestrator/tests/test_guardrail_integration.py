"""Guardrail integration in the orchestrator — input block, input redact,
output block branches. Builds on the Phase 3 orchestrator test scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelRequest,
    ModelResponse,
    ModelTier,
    ModelUsage,
    PromptTemplate,
    TokenBudget,
    UserRequest,
)
from meridian_guardrails import (
    GuardrailDecision,
    GuardrailOutcome,
    GuardrailPipeline,
    RegexPIIInputGuardrail,
    RegexPIIOutputGuardrail,
)
from meridian_orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    OrchestratorStatus,
    TemplateProvider,
)
from meridian_retrieval_client import MockRetrievalClient
from meridian_retrieval_client.mock import FixtureEntry

REPO_ROOT = Path(__file__).resolve().parents[3]


class FileTemplateProvider(TemplateProvider):
    def get_active(self, name: str, environment: str) -> PromptTemplate:
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
                environment=environment,
                status=ActivationStatus.DRAFT,
                canary_percentage=0,
                activated_at=datetime.now(tz=UTC),
                activated_by="t@t.com",
            ),
        )


@dataclass
class ScriptedModel:
    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[ModelRequest] = field(default_factory=list)

    def chat(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        content = self.responses.get(request.model, {})
        return ModelResponse(
            id="stub",
            model=request.model,
            content=content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=1,
        )


def _retrieval():  # type: ignore[no-untyped-def]
    return MockRetrievalClient(
        fixtures=[
            FixtureEntry(
                match="",
                chunks=[],  # intentionally empty — guardrail path is what's under test
            )
        ]
    )


def _user_request(query: str) -> UserRequest:
    return UserRequest(
        request_id="req_g001",
        user_id="u",
        session_id="s",
        query=query,
    )


@dataclass
class _AlwaysBlock:
    name: str = "always_block"

    def check(self, text: str) -> GuardrailOutcome:
        return GuardrailOutcome(decision=GuardrailDecision.BLOCK, reason="test policy")


@dataclass
class _AlwaysBlockOutput:
    name: str = "always_block_output"

    def check(self, text: str, *, context: dict[str, str]) -> GuardrailOutcome:
        return GuardrailOutcome(decision=GuardrailDecision.BLOCK, reason="output policy")


def test_input_guardrail_block_short_circuits_to_blocked_status() -> None:
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_retrieval(),
        model_client=ScriptedModel(),  # should never be called
        input_guardrails=GuardrailPipeline(guardrails=[_AlwaysBlock()]),
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("some request"))
    assert reply.status is OrchestratorStatus.BLOCKED
    assert reply.input_guardrail_result is not None
    assert reply.input_guardrail_result.is_blocked


def test_input_redact_flows_redacted_query_downstream() -> None:
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "reasoning": "",
                "answer": "no relevant docs were retrieved",
                "citations": [],
                "confidence": 0.8,
                "needs_escalation": False,
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_retrieval(),
        model_client=model,
        input_guardrails=GuardrailPipeline(guardrails=[RegexPIIInputGuardrail()]),
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("reach me at alice@example.com for the escalation"))
    # PII was redacted, not blocked — orchestrator proceeds.
    assert reply.status in (OrchestratorStatus.OK, OrchestratorStatus.FAILED)
    assert reply.input_guardrail_result is not None
    assert reply.input_guardrail_result.was_redacted
    # The classifier call must have seen the redacted text.
    small_calls = [c for c in model.calls if c.model == "meridian-small"]
    assert small_calls, "classifier was not invoked"
    user_msgs = [m for m in small_calls[0].messages if m.role == "user"]
    assert user_msgs
    assert "<EMAIL>" in user_msgs[0].content
    assert "alice@example.com" not in user_msgs[0].content


def test_output_guardrail_block_converts_ok_to_blocked() -> None:
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "reasoning": "",
                "answer": "answer that will get blocked",
                "citations": [],
                "confidence": 0.9,
                "needs_escalation": False,
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_retrieval(),
        model_client=model,
        output_guardrails=GuardrailPipeline(guardrails=[_AlwaysBlockOutput()]),
        config=OrchestratorConfig(environment="test"),
    )
    reply = orch.handle(_user_request("any question"))
    assert reply.status is OrchestratorStatus.BLOCKED
    assert reply.output_guardrail_result is not None
    assert reply.output_guardrail_result.is_blocked


def test_pii_output_guard_blocks_when_model_leaks_new_pii() -> None:
    model = ScriptedModel(
        responses={
            "meridian-small": {"intent": "grounded_qa", "confidence": 0.95, "model_tier": "mid"},
            "meridian-mid": {
                "reasoning": "",
                "answer": "Contact bob@company.com for more details.",
                "citations": [],
                "confidence": 0.9,
                "needs_escalation": False,
            },
        }
    )
    orch = Orchestrator(
        templates=FileTemplateProvider(),
        retrieval=_retrieval(),
        model_client=model,
        output_guardrails=GuardrailPipeline(guardrails=[RegexPIIOutputGuardrail()]),
        config=OrchestratorConfig(environment="test"),
    )
    # Input has no email — so the email in the output is a leak.
    reply = orch.handle(_user_request("Who owns the billing service?"))
    assert reply.status is OrchestratorStatus.BLOCKED
    assert reply.output_guardrail_result is not None
