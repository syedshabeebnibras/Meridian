# Orchestration

The orchestrator is Meridian's deterministic state machine — the single entry point a UserRequest flows through before a reply is returned. Canonical reference: **Sections 5 and 7** of `meridian-execution-plan.md`. This doc is the map from the plan to the code.

---

## State machine

```
    RECEIVED
       │
       ▼
    INPUT_GUARDRAILS      (stub pass-through; real checks Phase 5)
       │
       ▼
    CLASSIFIED            (small-tier classifier → Intent + confidence + suggested tier)
       │
       ▼  ───► REFUSED if confidence < 0.6
       │
    RETRIEVED             (MockRetrievalClient in Phase 3; real RAG Phase 4)
       │
       ▼
    ASSEMBLED             (PromptAssembler applies token budget + truncation)
       │
       ▼
    DISPATCHED            (ModelClient — retry + circuit-breaker injected at the edge)
       │
       ▼  ───► 1 corrective retry on VALIDATED failure
    VALIDATED             (OutputValidator: schema · citations · refusal · length · format)
       │
       ▼
    OUTPUT_GUARDRAILS     (stub pass-through; real checks Phase 5)
       │
       ▼
    SHAPED  →  COMPLETED
```

Any unrecoverable error routes to FAILED with a typed `OrchestratorReply` — the orchestrator never leaks an exception to the caller.

---

## Key files

| Concern | Location |
|---|---|
| `Orchestrator` class | `services/orchestrator/src/meridian_orchestrator/orchestrator.py` |
| Routing (`route_tier`) | `services/orchestrator/src/meridian_orchestrator/routing.py` |
| Retry policy | `services/model-gateway/src/meridian_model_gateway/retry.py` |
| Circuit breaker | `services/model-gateway/src/meridian_model_gateway/circuit.py` |
| `LiteLLMClient` | `services/model-gateway/src/meridian_model_gateway/client.py` |
| Resilient stack factory | `services/model-gateway/src/meridian_model_gateway/resilient.py` |
| Output validator | `packages/output-validator/src/meridian_output_validator/validator.py` |
| Mock retrieval | `services/retrieval-client/src/meridian_retrieval_client/mock.py` |

---

## Model routing (Section 7)

```python
from meridian_orchestrator.routing import route_tier

tier = route_tier(
    classification,
    retrieved_doc_count=len(retrieval.results),
)
# None  → refuse (confidence < 0.6)
# SMALL / MID / FRONTIER → dispatch to that tier's LiteLLM alias
```

Decision order:
1. **Confidence < 0.6** → refuse.
2. `out_of_scope` / `clarification` intent → force SMALL.
3. `grounded_qa` with more than 3 retrieved docs → force FRONTIER.
4. **Confidence 0.6–0.85** → upgrade one tier from what the classifier suggested.
5. **Confidence ≥ 0.85** → keep the classifier's tier.

Tier aliases map to the Phase 1 LiteLLM config:

| Tier | LiteLLM alias | Primary model | Secondary |
|---|---|---|---|
| small | `meridian-small` | `anthropic/claude-haiku-4-5` | `openai/gpt-4o-mini` |
| mid | `meridian-mid` | `anthropic/claude-sonnet-4-6` | `openai/gpt-4o` |
| frontier | `meridian-frontier` | `anthropic/claude-opus-4-7` | `openai/gpt-4o` |

---

## Retry + circuit breaker

Wrap the LiteLLM client to get the full Section 7 resilience stack:

```python
from meridian_model_gateway import resilient_client

client = resilient_client()  # CircuitBreaker → RetryingClient → LiteLLMClient
```

**Retry policy** (Section 7 §Retry):

| Scenario | Max retries | Backoff ladder |
|---|---|---|
| 429 | 3 | 1s · 3s · 9s (±25% jitter) |
| 5xx | 2 | 2s · 6s |
| 4xx (non-429) | 0 | — |
| Timeout / connect error | 1 | 0.5s |

**Circuit breaker** (Section 7 §Circuit breakers):
- `CLOSED` → counts failures in a 60s rolling window.
- 3 failures → `OPEN`; every call rejected with `CircuitOpenError` for 30s.
- After cooldown → `HALF_OPEN`; a single probe succeeds → `CLOSED`, fails → `OPEN` again.

When the circuit is open, the orchestrator replies with `OrchestratorStatus.DEGRADED` and a user-friendly "temporarily unavailable" message.

---

## Output validation (Section 7 §Output validation)

Every model response goes through `OutputValidator.validate(...)`:

1. **Schema check** — `content` matches the declared JSON Schema. Error if not.
2. **Citation check** — every `[DOC-N]` in the answer maps to a retrieved chunk; every `citations[].source_title` is in the retrieved set. Missing or hallucinated citations fail.
3. **Refusal check** — low-confidence responses must be explicit refusals, not fabricated answers.
4. **Length check** — answer within min/max char bounds. Too-long is a warning (not a fail).
5. **Format check** — citation list is a list of dicts.

Each issue has `severity: "error" | "warning"`. Only `error` issues fail validation. The orchestrator does **one** corrective retry (Section 7) — the retry appends the validator's error messages as a user-role nudge so the model can regenerate.

---

## Constructing an Orchestrator

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meridian_model_gateway import resilient_client
from meridian_orchestrator import Orchestrator, OrchestratorConfig, TemplateProvider
from meridian_prompt_registry import PromptRegistry
from meridian_retrieval_client import MockRetrievalClient

class RegistryTemplateProvider(TemplateProvider):
    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry
    def get_active(self, name, environment):
        return self._registry.get_active(name, environment)

engine = create_engine(DATABASE_URL, future=True)
session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

orch = Orchestrator(
    templates=RegistryTemplateProvider(PromptRegistry(session_factory)),
    retrieval=MockRetrievalClient.from_yaml(Path("datasets/retrieval_fixtures.yaml")),
    model_client=resilient_client(),
    config=OrchestratorConfig(environment="dev"),
)

reply = orch.handle(user_request)
```

`reply` is an `OrchestratorReply` with:
- `status` — `ok` / `refused` / `blocked` / `degraded` / `failed`
- `model_response` — the full `ModelResponse` (content, usage, latency)
- `orchestration_state` — Section 8's `OrchestrationState` with per-stage timings
- `validation` — `ValidationResult` with any issues
- `error_message` — user-facing text for non-OK statuses

---

## Phase 3 scope boundary

**In this phase:**
- State machine with 10 phases, deterministic
- Model routing (tier bump, retrieval-count override, refusal threshold)
- Retry + circuit breaker at the gateway edge
- Output validation + 1 corrective retry
- Degraded-mode envelope
- Mock retrieval client
- 14 integration tests covering happy path, refusal, tier bump, corrective retry, 429 failover, circuit-open degrade, p95 latency

**Not in this phase** (pointers):
- Real RAG pipeline → Phase 4
- Real guardrails (Presidio, Llama Guard, Patronus) → Phase 5
- Real tool execution (Jira, Slack) → Phase 4
- Async orchestration + streaming SSE → Phase 6
- Semantic response cache → deferred; degraded mode is a direct "unavailable" message
- OTel span emission → Phase 6
- Cost / latency circuit breakers (in addition to the provider breaker) → Phase 6
