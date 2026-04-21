# Architecture

Meridian is a deterministic orchestration engine with three-tier model routing, a self-hosted LiteLLM gateway, a Postgres-backed prompt registry, and Langfuse-powered observability. The canonical reference is **Section 5 of [`meridian-execution-plan.md`](./meridian-execution-plan.md)**. This file is a map from the plan to the code.

---

## Components

| Component | Code location | Responsibility | Phase |
|---|---|---|---|
| API Gateway | *external* | Auth, rate limiting, request routing | out of scope |
| Orchestration Service | `services/orchestrator/` | State machine: classify → retrieve → assemble → dispatch → validate → shape | Phase 3 |
| Prompt Registry | `services/prompt-registry/` + `packages/db/` | Versioned, immutable prompt templates with activation rollback | Phase 2 |
| Model Gateway | `services/model-gateway/` | Thin client over the LiteLLM proxy; retry / failover / instrumentation | Phase 3 |
| Retrieval Client | `services/retrieval-client/` | Consumes the RAG pipeline via the contract in Section 8 | Phase 4 |
| Tool Executor | `services/tool-executor/` | Schema-validated tool calls (Jira, Slack, internal APIs) | Phase 4 |
| Guardrail Pipeline | `packages/guardrails/` | Input + output guardrails (Presidio, Llama Guard, Patronus) | Phase 5 |
| Evaluation Pipeline | `services/evaluator/` | Regression + online sampling + LLM-judge calibration | Phase 5 |
| Telemetry | `packages/telemetry/` | OTel spans with GenAI semantic conventions | Phase 6 (attrs defined in Phase 1) |
| Shared contracts | `packages/contracts/` | Pydantic v2 models for every wire payload | **Phase 1 ✓** |
| Data layer | `packages/db/` + `migrations/` | SQLAlchemy ORM + Alembic migrations | **Phase 1 ✓** |
| Dev infrastructure | `docker-compose.yml`, `infra/` | Postgres+pgvector, Redis, LiteLLM, Langfuse v3 | **Phase 1 ✓** |

---

## Request lifecycle

The state machine matches Section 5's lifecycle diagram. Each phase is an enum value in `meridian_contracts.orchestration.OrchestratorPhase`:

```
RECEIVED
  → INPUT_GUARDRAILS   (Presidio PII + Llama Guard injection check — Phase 5)
  → CLASSIFIED         (small-tier classifier assigns Intent + ModelTier — Phase 3)
  → RETRIEVED          (RAG call, rerank, threshold filter — Phase 4)
  → ASSEMBLED          (template + retrieved docs + history + query — Phase 2)
  → DISPATCHED         (LiteLLM call with retry/failover — Phase 3)
  → VALIDATED          (JSON-schema check + faithfulness check — Phase 3 / Phase 5)
  → OUTPUT_GUARDRAILS  (toxicity + PII leak — Phase 5)
  → SHAPED             (citation formatting + API envelope — Phase 3)
  → COMPLETED
```

Any phase may transition to `FAILED` and emit a graceful-degradation response.

---

## Data layer

Three schemas are live after the initial migration (`migrations/versions/0001_initial_schema.py`):

- **`prompt_templates`** + **`prompt_activations`** — the prompt registry. Templates are immutable; activations carry the (environment, status, canary_percentage) that decides which version serves traffic. Rollback is a row update in `prompt_activations`, not a DDL event.
- **`eval_results`** — persisted `EvaluationRecord` rows from offline regression runs, online sampling, golden runs, and safety evals.
- **`audit_log`** — append-only request/response trail for compliance (Section 9).

`pgvector` is enabled on the `meridian` database so the Phase 2 semantic cache (Section 5, three-layer cache) can add its table without a new migration for extensions.

---

## Observability

`meridian_telemetry.semconv` defines every attribute key we will emit on spans. Attributes are grouped into:

- `GenAIAttr` — OTel GenAI semantic convention keys (`gen_ai.system`, `gen_ai.request.model`, token usage, etc.)
- `MeridianAttr` — Meridian-specific keys (`meridian.request_id`, `meridian.prompt_version`, `meridian.cost_usd`, `meridian.cache_hit`, etc.)

The telemetry backend is self-hosted Langfuse v3 (Section 19 D9). The dev stack in `docker-compose.yml` runs `langfuse-web` + `langfuse-worker` on top of the shared Postgres + Redis + Clickhouse + MinIO.

---

## Model routing

`infra/litellm/config.yaml` declares three model aliases: `meridian-small`, `meridian-mid`, `meridian-frontier`. Each alias has two backing models (Anthropic priority 1, OpenAI priority 2) so LiteLLM fails over transparently on provider outage. The orchestrator never references a concrete model ID directly — it routes by tier.
