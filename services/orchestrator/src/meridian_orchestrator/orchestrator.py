"""Orchestrator — deterministic state machine (Sections 5 + 7).

Phases mirror OrchestratorPhase:

  RECEIVED
  ↓ INPUT_GUARDRAILS      (stub pass-through; real checks Phase 5)
  ↓ CLASSIFIED            (small-tier call; fallback classification on failure)
  ↓ RETRIEVED             (mock retrieval for Phase 3)
  ↓ ASSEMBLED             (PromptAssembler)
  ↓ DISPATCHED            (ModelClient — retry + circuit breaker injected)
  ↓ VALIDATED             (OutputValidator; 1 corrective retry)
  ↓ OUTPUT_GUARDRAILS     (stub pass-through)
  ↓ SHAPED                (build OrchestratorReply)
  ↓ COMPLETED

Any unrecoverable error routes to FAILED with a degraded reply so the caller
always gets a typed response, never an exception.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from meridian_contracts import (
    ClassificationResult,
    ConversationTurn,
    DispatchInfo,
    Intent,
    ModelRequest,
    ModelResponse,
    ModelTier,
    ModelUsage,
    OrchestrationState,
    OrchestratorPhase,
    PromptAssemblyInfo,
    PromptTemplate,
    ResponseFormat,
    RetrievalSummary,
    ToolInvocation,
    ToolResult,
    ToolValidation,
    UserRequest,
)
from meridian_cost_accounting import (
    CostAccountant,
    CostBreakerState,
    CostCircuitBreaker,
    PerUserDailyTracker,
)
from meridian_guardrails import GuardrailPipeline, PipelineResult
from meridian_model_gateway import CircuitOpenError, ModelClient, ModelDispatchError
from meridian_output_validator import OutputValidator, ValidationResult
from meridian_prompt_assembler import Assembler, AssemblyContext
from meridian_retrieval_client import RetrievalClient
from meridian_semantic_cache import CacheHit, SemanticCache
from meridian_session_store import SessionStore
from meridian_telemetry import Tracer
from meridian_tool_executor import (
    InvalidParametersError,
    NeedsConfirmationError,
    ToolExecutor,
    UnknownToolError,
)
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Reply envelope
# ---------------------------------------------------------------------------
class OrchestratorStatus(StrEnum):
    OK = "ok"
    REFUSED = "refused"
    BLOCKED = "blocked"  # guardrails (Phase 5)
    DEGRADED = "degraded"  # all providers down
    FAILED = "failed"
    PENDING_CONFIRMATION = "pending_confirmation"  # destructive tool awaiting user OK


class OrchestratorReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    trace_id: str | None = None
    status: OrchestratorStatus
    model_response: ModelResponse | None = None
    orchestration_state: OrchestrationState
    validation: ValidationResult | None = None
    error_message: str | None = None
    tool_invocation: ToolInvocation | None = None
    tool_result: ToolResult | None = None
    clarification_question: str | None = None
    input_guardrail_result: PipelineResult | None = None
    output_guardrail_result: PipelineResult | None = None
    cost_usd: float | None = None


# ---------------------------------------------------------------------------
# Template provider — decouples orchestrator from Postgres
# ---------------------------------------------------------------------------
class TemplateProvider:
    """Anything that can hand the orchestrator a PromptTemplate by name."""

    def get_active(self, name: str, environment: str) -> PromptTemplate:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Routing schema constants (duplicated from evaluator to avoid a cross-dep).
# ---------------------------------------------------------------------------
# OpenAI's strict-mode structured output (and Anthropic's) requires every
# object-typed subschema to include `additionalProperties: false` and to
# list every property in `required`. The schemas below follow that rule.
_CLASSIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string"},
        "confidence": {"type": "number"},
        "model_tier": {"type": "string"},
    },
    "required": ["intent", "confidence", "model_tier"],
}

_GROUNDED_QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "doc_index": {"type": "integer"},
                    "source_title": {"type": "string"},
                    "relevant_excerpt": {"type": "string"},
                },
                "required": ["doc_index", "source_title", "relevant_excerpt"],
            },
        },
        "confidence": {"type": "number"},
        "needs_escalation": {"type": "boolean"},
    },
    "required": ["reasoning", "answer", "citations", "confidence", "needs_escalation"],
}

_TIER_ALIAS: dict[ModelTier, str] = {
    ModelTier.SMALL: "meridian-small",
    ModelTier.MID: "meridian-mid",
    ModelTier.FRONTIER: "meridian-frontier",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class OrchestratorConfig:
    environment: str = "dev"
    classifier_prompt_name: str = "classifier"
    grounded_qa_prompt_name: str = "grounded_qa"
    tool_invocation_prompt_name: str = "tool_invocation"
    refusal_threshold: float = 0.6
    upgrade_threshold: float = 0.85
    max_corrective_retries: int = 1
    # Per-stage timeout budgets (wall-clock seconds, Section 7 §Timeouts).
    input_guardrail_timeout_s: float = 0.5
    classification_timeout_s: float = 3.0
    retrieval_timeout_s: float = 2.0
    assembly_timeout_s: float = 1.0
    dispatch_timeout_s: float = 30.0
    validation_timeout_s: float = 1.0
    output_guardrail_timeout_s: float = 0.5
    total_request_timeout_s: float = 45.0


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------
@dataclass
class Orchestrator:
    """Runs a UserRequest through the full state machine."""

    templates: TemplateProvider
    retrieval: RetrievalClient
    model_client: ModelClient
    tool_executor: ToolExecutor | None = None  # None disables tool flow
    input_guardrails: GuardrailPipeline | None = None
    output_guardrails: GuardrailPipeline | None = None
    tracer: Tracer = field(default_factory=Tracer)
    cost_accountant: CostAccountant | None = None
    user_spend_tracker: PerUserDailyTracker | None = None
    cost_breaker: CostCircuitBreaker | None = None
    session_store: SessionStore | None = None
    semantic_cache: SemanticCache | None = None
    validator: OutputValidator = field(default_factory=OutputValidator)
    assembler: Assembler = field(default_factory=Assembler)
    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    clock: Callable[[], float] = time.perf_counter
    wall_clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------
    def handle(self, request: UserRequest) -> OrchestratorReply:
        state = OrchestrationState(
            request_id=request.request_id,
            current_state=OrchestratorPhase.RECEIVED,
        )
        started = self.clock()
        timings = state.timings_ms

        # Hydrate conversation_history from the session store if the caller
        # didn't supply one inline. An explicit list (even empty-on-purpose in
        # some edge cases) is respected; we only backfill when empty.
        if (
            self.session_store is not None
            and not request.conversation_history
            and request.session_id
        ):
            hydrated = self.session_store.get(request.session_id)
            if hydrated:
                request = request.model_copy(update={"conversation_history": hydrated})

        input_guardrail_result: PipelineResult | None = None
        try:
            # ----- Input guardrails -----
            state.current_state = OrchestratorPhase.INPUT_GUARDRAILS
            effective_query = request.query
            if self.input_guardrails is not None:
                input_guardrail_result = self.input_guardrails.check_input(request.query)
                if input_guardrail_result.is_blocked:
                    state.current_state = OrchestratorPhase.FAILED
                    timings.input_guardrails = self._stage_ms(started)
                    timings.total = timings.input_guardrails
                    return OrchestratorReply(
                        request_id=request.request_id,
                        status=OrchestratorStatus.BLOCKED,
                        orchestration_state=state,
                        input_guardrail_result=input_guardrail_result,
                        error_message="Your request was blocked by an input safety check.",
                    )
                effective_query = input_guardrail_result.effective_text
            timings.input_guardrails = self._stage_ms(started)

            # ----- Classify -----
            state.current_state = OrchestratorPhase.CLASSIFIED
            classification = self._classify(effective_query)
            state.classification = classification
            timings.classification = self._stage_ms(started, previous=timings.input_guardrails)

            # ----- Route or refuse early -----
            from meridian_orchestrator.routing import route_tier

            # Retrieval count isn't known yet, so route optimistically with 0.
            # We'll re-check after retrieval.
            tentative_tier = route_tier(
                classification,
                retrieved_doc_count=0,
                refusal_threshold=self.config.refusal_threshold,
                upgrade_threshold=self.config.upgrade_threshold,
            )
            if tentative_tier is None:
                return self._refuse(state, classification)

            # ----- Tool-action branch (Phase 4) -----
            if classification.intent is Intent.TOOL_ACTION and self.tool_executor is not None:
                return self._handle_tool_action(request, state, classification, started)

            # ----- Retrieve -----
            state.current_state = OrchestratorPhase.RETRIEVED
            retrieval = self.retrieval.retrieve(effective_query, top_k=10)
            state.retrieval = RetrievalSummary(
                query_rewritten=retrieval.query_rewritten,
                chunks_retrieved=retrieval.total_chunks_retrieved,
                chunks_after_rerank=retrieval.total_after_rerank,
                top_relevance_score=(
                    retrieval.results[0].relevance_score if retrieval.results else 0.0
                ),
            )
            timings.retrieval = self._stage_ms(started, previous=timings.classification)

            # Re-route now that we know retrieval count.
            tier = route_tier(
                classification,
                retrieved_doc_count=len(retrieval.results),
                refusal_threshold=self.config.refusal_threshold,
                upgrade_threshold=self.config.upgrade_threshold,
            )
            assert tier is not None  # already validated above

            # Cost circuit breaker: when daily spend has exceeded the overrun
            # ratio, degrade FRONTIER to MID rather than 503'ing. We still
            # serve an answer — just with a cheaper model.
            if (
                self.cost_breaker is not None
                and tier is ModelTier.FRONTIER
                and self.cost_breaker.state is CostBreakerState.OPEN
            ):
                state.errors.append("cost_breaker_open: degraded frontier → mid")
                tier = ModelTier.MID

            # Semantic cache: partition by the sorted retrieved chunk IDs so
            # two answers grounded in different sources can't collide. On a
            # hit we skip assembly + dispatch entirely and return the stored
            # ModelResponse wrapped in a fresh OrchestratorReply.
            cached_reply = self._try_semantic_cache_lookup(
                effective_query, retrieval.results, request, state, started
            )
            if cached_reply is not None:
                return cached_reply

            # ----- Assemble -----
            state.current_state = OrchestratorPhase.ASSEMBLED
            template = self.templates.get_active(
                self.config.grounded_qa_prompt_name, self.config.environment
            )
            template = _override_tier(template, tier)
            context = AssemblyContext(
                user_query=effective_query,
                retrieved_docs=retrieval.results,
                conversation_history=list(request.conversation_history),
                few_shot_examples=[],
                system_vars={"company_name": request.metadata.get("company_name", "Meridian Labs")},
            )
            assembled = self.assembler.assemble(template, context)
            state.prompt = PromptAssemblyInfo(
                template_name=template.name,
                template_version=template.version,
                total_tokens_assembled=assembled.total_tokens,
                cache_prefix_tokens=assembled.token_counts.get("system", 0),
            )
            timings.assembly = self._stage_ms(started, previous=timings.retrieval)

            # ----- Dispatch (+ 1 corrective retry on validation failure) -----
            state.current_state = OrchestratorPhase.DISPATCHED
            dispatch = DispatchInfo(
                model=_TIER_ALIAS[tier],
                provider="anthropic",  # LiteLLM handles provider failover internally
                attempt=1,
                idempotency_key=f"{request.request_id}_a1",
            )
            state.dispatch = dispatch
            model_response, validation, corrective_used = self._dispatch_with_validation(
                assembled=assembled,
                retrieval_results=retrieval.results,
                template=template,
                request=request,
                tier=tier,
                state=state,
            )
            timings.dispatch_pending = self._stage_ms(started, previous=timings.assembly)

            # ----- Validation has already run in _dispatch_with_validation -----
            state.current_state = OrchestratorPhase.VALIDATED
            timings.validation = self._stage_ms(started, previous=timings.dispatch_pending)

            # ----- Output guardrails -----
            state.current_state = OrchestratorPhase.OUTPUT_GUARDRAILS
            output_guardrail_result: PipelineResult | None = None
            if self.output_guardrails is not None:
                answer_text = _extract_answer_text(model_response)
                retrieved_blob = "\n".join(d.content for d in retrieval.results)
                output_guardrail_result = self.output_guardrails.check_output(
                    answer_text,
                    context={
                        "input_text": request.query,
                        "retrieved_docs_text": retrieved_blob,
                    },
                )
                if output_guardrail_result.is_blocked:
                    state.current_state = OrchestratorPhase.FAILED
                    timings.output_guardrails = self._stage_ms(started, previous=timings.validation)
                    timings.total = self._stage_ms(started)
                    return OrchestratorReply(
                        request_id=request.request_id,
                        status=OrchestratorStatus.BLOCKED,
                        model_response=model_response,
                        orchestration_state=state,
                        validation=validation,
                        input_guardrail_result=input_guardrail_result,
                        output_guardrail_result=output_guardrail_result,
                        error_message="Response was blocked by an output safety check.",
                    )
                if output_guardrail_result.was_redacted:
                    model_response = _replace_answer(
                        model_response, output_guardrail_result.effective_text
                    )
            timings.output_guardrails = self._stage_ms(started, previous=timings.validation)

            # ----- Shape and return -----
            state.current_state = OrchestratorPhase.SHAPED
            state.current_state = OrchestratorPhase.COMPLETED
            timings.total = self._stage_ms(started)
            status = OrchestratorStatus.OK if validation.valid else OrchestratorStatus.FAILED
            cost_usd = self._account_cost(model_response, request.user_id)
            if status is OrchestratorStatus.OK:
                self._persist_turns(request, model_response)
                self._store_in_semantic_cache(effective_query, retrieval.results, model_response)
            return OrchestratorReply(
                request_id=request.request_id,
                status=status,
                model_response=model_response,
                orchestration_state=state,
                validation=validation,
                input_guardrail_result=input_guardrail_result,
                output_guardrail_result=output_guardrail_result,
                cost_usd=cost_usd,
                error_message=(
                    None if validation.valid else "output validation failed after corrective retry"
                )
                if corrective_used
                else None,
            )

        except CircuitOpenError as exc:
            state.errors.append(str(exc))
            state.current_state = OrchestratorPhase.FAILED
            timings.total = self._stage_ms(started)
            return OrchestratorReply(
                request_id=request.request_id,
                status=OrchestratorStatus.DEGRADED,
                orchestration_state=state,
                error_message="Meridian is temporarily unavailable. Please try again shortly.",
            )
        except ModelDispatchError as exc:
            state.errors.append(str(exc))
            state.current_state = OrchestratorPhase.FAILED
            timings.total = self._stage_ms(started)
            return OrchestratorReply(
                request_id=request.request_id,
                status=OrchestratorStatus.FAILED,
                orchestration_state=state,
                error_message=f"model dispatch failed: {exc}",
            )

    # ------------------------------------------------------------------
    # classification
    # ------------------------------------------------------------------
    def _classify(self, query: str) -> ClassificationResult:
        template = self.templates.get_active(
            self.config.classifier_prompt_name, self.config.environment
        )
        context = AssemblyContext(user_query=query, few_shot_examples=[])
        assembled = self.assembler.assemble(template, context)
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
                    "schema": _CLASSIFIER_SCHEMA,
                },
            ),
            metadata={"prompt_version": f"{template.name}_v{template.version}"},
        )
        try:
            response = self.model_client.chat(request)
        except Exception:
            # Classifier failure — safe default (mid-tier grounded_qa with
            # modest confidence so downstream routing upgrades it).
            return ClassificationResult(
                intent=Intent.GROUNDED_QA,
                confidence=0.7,
                model_tier=ModelTier.MID,
                workflow="grounded_qa_fallback",
            )
        return _parse_classification(response)

    # ------------------------------------------------------------------
    # dispatch + 1 corrective retry
    # ------------------------------------------------------------------
    def _dispatch_with_validation(
        self,
        *,
        assembled: Any,
        retrieval_results: list[Any],
        template: PromptTemplate,
        request: UserRequest,
        tier: ModelTier,
        state: OrchestrationState,
    ) -> tuple[ModelResponse, ValidationResult, bool]:
        """Dispatch once, validate, retry once with a corrective nudge if invalid.

        Returns (response, validation, corrective_retry_used).
        """
        for attempt in range(self.config.max_corrective_retries + 2):
            model_request = ModelRequest(
                model=_TIER_ALIAS[tier],
                messages=[{"role": m.role, "content": m.content} for m in assembled.messages],
                max_tokens=1024,
                temperature=0.1,
                response_format=ResponseFormat(
                    type="json_schema",
                    json_schema={
                        "name": template.schema_ref,
                        "strict": True,
                        "schema": _GROUNDED_QA_SCHEMA,
                    },
                ),
                metadata={
                    "prompt_version": f"{template.name}_v{template.version}",
                    "request_id": request.request_id,
                },
            )
            response = self.model_client.chat(model_request)
            validation = self.validator.validate(
                response,
                schema=_GROUNDED_QA_SCHEMA,
                retrieved_docs=retrieval_results,
            )
            if validation.valid:
                return response, validation, attempt > 0

            if attempt >= self.config.max_corrective_retries:
                return response, validation, True

            # Inject a corrective nudge for the retry.
            issues = "; ".join(i.message for i in validation.issues if i.severity == "error")
            corrective = (
                f"Your previous response had validation issues: {issues}. "
                "Please regenerate using the required JSON schema."
            )
            assembled.messages.append(
                type(assembled.messages[-1])(
                    role="user", content=corrective, cache_breakpoint_after=False
                )
            )

        # Unreachable, but satisfies mypy.
        raise RuntimeError("dispatch loop exhausted without return")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _stage_ms(self, started: float, *, previous: int | None = None) -> int:
        elapsed_ms = int((self.clock() - started) * 1000)
        return elapsed_ms - (previous or 0)

    def _semantic_cache_partition_key(self, docs: list[Any]) -> str:
        """Partition key = sorted retrieved chunk IDs, joined.

        Queries answered against disjoint doc sets must not share a cache
        entry — otherwise the same question across two tenants' docs
        would bleed. When no docs were retrieved, we use a sentinel so
        un-grounded answers bucket together.
        """
        if not docs:
            return "no-docs"
        return "|".join(sorted(getattr(d, "chunk_id", "") for d in docs))

    def _try_semantic_cache_lookup(
        self,
        query: str,
        docs: list[Any],
        request: UserRequest,
        state: OrchestrationState,
        started: float,
    ) -> OrchestratorReply | None:
        """Check the semantic cache; on HIT return a short-circuit reply.

        Returns None on MISS or when the cache isn't configured."""
        if self.semantic_cache is None:
            return None
        partition = self._semantic_cache_partition_key(docs)
        result = self.semantic_cache.lookup(query=query, partition_key=partition)
        if not isinstance(result, CacheHit):
            return None
        state.current_state = OrchestratorPhase.COMPLETED
        state.timings_ms.total = self._stage_ms(started)
        # Reuse the minimum shape — downstream consumers of OrchestratorReply
        # don't need a full ModelResponse on a cache hit (no token counts).
        cached_response = ModelResponse(
            id=f"cache_{request.request_id}",
            model="cache",
            content=result.response_content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=0,
        )
        self._persist_turns(request, cached_response)
        return OrchestratorReply(
            request_id=request.request_id,
            status=OrchestratorStatus.OK,
            model_response=cached_response,
            orchestration_state=state,
            cost_usd=0.0,
        )

    def _store_in_semantic_cache(
        self,
        query: str,
        docs: list[Any],
        response: ModelResponse,
    ) -> None:
        if self.semantic_cache is None:
            return
        partition = self._semantic_cache_partition_key(docs)
        self.semantic_cache.store(
            query=query,
            partition_key=partition,
            response_content=response.content,
        )

    def _persist_turns(self, request: UserRequest, response: ModelResponse) -> None:
        """Append the user turn + assistant turn to the session store on success.

        Skipped when no store is wired or no session_id is present. The
        assistant text is the natural-language answer extracted from the
        structured response; if the response has no plain-text answer (e.g.
        tool responses), we persist an empty string placeholder so the turn
        still roundtrips.
        """
        if self.session_store is None or not request.session_id:
            return
        now = self.wall_clock()
        user_turn = ConversationTurn(role="user", content=request.query, timestamp=now)
        assistant_turn = ConversationTurn(
            role="assistant",
            content=_extract_answer_text(response),
            timestamp=now,
        )
        self.session_store.append(request.session_id, user_turn)
        self.session_store.append(request.session_id, assistant_turn)

    def _account_cost(self, response: ModelResponse, user_id: str) -> float | None:
        """If cost accounting is configured, compute per-request cost and update
        the per-user daily tracker + global cost breaker. Returns USD as a
        float or None if disabled."""
        if self.cost_accountant is None:
            return None
        breakdown = self.cost_accountant.cost_of(response)
        if self.user_spend_tracker is not None:
            self.user_spend_tracker.record(user_id, breakdown.total_usd)
        if self.cost_breaker is not None:
            self.cost_breaker.record(breakdown.total_usd)
        return float(breakdown.total_usd)

    def _refuse(
        self, state: OrchestrationState, classification: ClassificationResult
    ) -> OrchestratorReply:
        state.current_state = OrchestratorPhase.COMPLETED
        return OrchestratorReply(
            request_id=state.request_id,
            status=OrchestratorStatus.REFUSED,
            orchestration_state=state,
            error_message=(
                f"I'm not confident I can answer this accurately "
                f"(confidence={classification.confidence:.2f}). "
                "Please try rephrasing or contact support."
            ),
        )

    # ------------------------------------------------------------------
    # tool-action branch
    # ------------------------------------------------------------------
    def _handle_tool_action(
        self,
        request: UserRequest,
        state: OrchestrationState,
        classification: ClassificationResult,
        started: float,
    ) -> OrchestratorReply:
        """Runs the tool_invocation template, validates, and executes.

        Destructive ops return PENDING_CONFIRMATION unless the client's
        UserRequest.metadata has ``confirmed=yes`` (the canonical way for
        the caller to opt in to a destructive action on the follow-up).
        """
        assert self.tool_executor is not None

        tool_template = self.templates.get_active(
            self.config.tool_invocation_prompt_name, self.config.environment
        )
        tool_defs = _render_tool_definitions(self.tool_executor)
        assembled = self.assembler.assemble(
            tool_template,
            AssemblyContext(
                user_query=request.query,
                conversation_history=list(request.conversation_history),
                system_vars={"tool_definitions_json": tool_defs},
            ),
        )
        state.prompt = PromptAssemblyInfo(
            template_name=tool_template.name,
            template_version=tool_template.version,
            total_tokens_assembled=assembled.total_tokens,
            cache_prefix_tokens=assembled.token_counts.get("system", 0),
        )
        state.current_state = OrchestratorPhase.DISPATCHED
        state.dispatch = DispatchInfo(
            model=_TIER_ALIAS[tool_template.model_tier],
            provider="anthropic",
            attempt=1,
            idempotency_key=f"{request.request_id}_tool_a1",
        )

        model_request = ModelRequest(
            model=_TIER_ALIAS[tool_template.model_tier],
            messages=[{"role": m.role, "content": m.content} for m in assembled.messages],
            max_tokens=512,
            temperature=0.1,
            metadata={
                "prompt_version": f"{tool_template.name}_v{tool_template.version}",
                "request_id": request.request_id,
            },
        )
        response = self.model_client.chat(model_request)
        parsed = _parse_tool_response(response)
        state.timings_ms.dispatch_pending = self._stage_ms(started)

        # Clarification branch — no tool call to validate.
        if parsed["action"] == "clarify":
            state.current_state = OrchestratorPhase.COMPLETED
            return OrchestratorReply(
                request_id=request.request_id,
                status=OrchestratorStatus.OK,
                model_response=response,
                orchestration_state=state,
                clarification_question=parsed.get("clarification_question"),
            )

        tool_call = parsed.get("tool_call") or {}
        invocation = ToolInvocation(
            tool_call_id=f"tc_{request.request_id}",
            tool_name=tool_call.get("tool_name", ""),
            parameters=tool_call.get("parameters", {}),
            requires_confirmation=bool(tool_call.get("requires_confirmation", False)),
            confirmation_message=tool_call.get("confirmation_message"),
            validation=ToolValidation(
                schema_valid=False,
                parameters_allowlisted=False,
                no_injection_detected=False,
            ),
        )

        state.current_state = OrchestratorPhase.VALIDATED
        try:
            validation = self.tool_executor.prepare(invocation)
        except (UnknownToolError, InvalidParametersError) as exc:
            state.errors.append(str(exc))
            state.current_state = OrchestratorPhase.FAILED
            return OrchestratorReply(
                request_id=request.request_id,
                status=OrchestratorStatus.FAILED,
                model_response=response,
                orchestration_state=state,
                tool_invocation=invocation,
                error_message=f"tool validation failed: {exc}",
            )
        invocation = invocation.model_copy(update={"validation": validation})

        confirmed = request.metadata.get("confirmed", "").lower() == "yes"

        # Destructive op without explicit confirmation → bounce back with the
        # confirmation prompt so the caller can render it to the user.
        if invocation.requires_confirmation and not confirmed:
            state.current_state = OrchestratorPhase.COMPLETED
            state.timings_ms.total = self._stage_ms(started)
            return OrchestratorReply(
                request_id=request.request_id,
                status=OrchestratorStatus.PENDING_CONFIRMATION,
                model_response=response,
                orchestration_state=state,
                tool_invocation=invocation,
                error_message=invocation.confirmation_message,
            )

        # Execute.
        try:
            tool_result = self.tool_executor.execute(
                invocation,
                request_id=request.request_id,
                confirmed=confirmed,
            )
        except NeedsConfirmationError as exc:
            state.errors.append(str(exc))
            state.current_state = OrchestratorPhase.FAILED
            return OrchestratorReply(
                request_id=request.request_id,
                status=OrchestratorStatus.FAILED,
                model_response=response,
                orchestration_state=state,
                tool_invocation=invocation,
                error_message=str(exc),
            )

        state.current_state = OrchestratorPhase.COMPLETED
        state.timings_ms.total = self._stage_ms(started)
        return OrchestratorReply(
            request_id=request.request_id,
            status=OrchestratorStatus.OK,
            model_response=response,
            orchestration_state=state,
            tool_invocation=invocation,
            tool_result=tool_result,
        )


def _extract_answer_text(response: ModelResponse) -> str:
    """Pull the natural-language answer out of a ModelResponse for guardrail scanning."""
    content = response.content
    if isinstance(content, dict):
        return str(content.get("answer", ""))
    return str(content)


def _replace_answer(response: ModelResponse, new_answer: str) -> ModelResponse:
    """Return a ModelResponse with the `answer` field replaced (for redaction)."""
    content = response.content
    if isinstance(content, dict):
        new_content = {**content, "answer": new_answer}
        return response.model_copy(update={"content": new_content})
    return response.model_copy(update={"content": new_answer})


def _parse_tool_response(response: ModelResponse) -> dict[str, Any]:
    """Pull the tool_invocation response JSON out of the model reply."""
    content = response.content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return {"action": "clarify", "clarification_question": content}
    if not isinstance(content, dict):
        return {"action": "clarify", "clarification_question": ""}
    return content


def _render_tool_definitions(executor: ToolExecutor) -> str:
    """Dump every registered tool's (name, schema, requires_confirmation) tuple
    as a JSON string for the prompt template."""
    tools = []
    for name in executor.registry.names():
        tool = executor.registry.get(name)
        tools.append(
            {
                "name": tool.name,
                "requires_confirmation": tool.requires_confirmation,
                "parameters_schema": tool.schema,
            }
        )
    return json.dumps(tools, indent=2)


def _parse_classification(response: ModelResponse) -> ClassificationResult:
    content = response.content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {}
    if not isinstance(content, dict):
        content = {}
    return ClassificationResult(
        intent=Intent(content.get("intent", Intent.GROUNDED_QA.value)),
        confidence=float(content.get("confidence", 0.7)),
        model_tier=ModelTier(content.get("model_tier", ModelTier.MID.value)),
        workflow=content.get("workflow", "grounded_qa"),
    )


def _override_tier(template: PromptTemplate, tier: ModelTier) -> PromptTemplate:
    """Return a copy of the template with a different model_tier.

    We keep the template's content/budgets/schema — only the tier (which
    maps to the LiteLLM alias) changes. This is how the routing decision
    flows back into dispatch without requiring a separate template per tier.
    """
    if template.model_tier is tier:
        return template
    return template.model_copy(update={"model_tier": tier})
