# Data Contracts

The canonical source of truth for every wire payload in Meridian lives in `packages/contracts/`, as Pydantic v2 models. JSON Schema is derived from the models, not hand-written.

Every model mirrors an example in **Section 8 of [`meridian-execution-plan.md`](./meridian-execution-plan.md)**, and every example in Section 8 is round-trip tested in `packages/contracts/tests/test_contracts_section_8.py`. If Section 8 changes, the test changes.

---

## Contract index

| Contract | Pydantic module | Purpose | Producers | Consumers |
|---|---|---|---|---|
| `UserRequest` | `user_request.py` | Inbound user query + prior conversation | API gateway | orchestrator |
| `OrchestrationState` | `orchestration.py` | Live state of a request through the state machine | orchestrator | orchestrator, tracing |
| `PromptTemplate` | `prompt_template.py` | Versioned template stored in the registry | admin / prompt authors | prompt registry, assembler |
| `ModelRequest` | `model.py` | OpenAI-compatible payload sent to LiteLLM | orchestrator / model gateway | LiteLLM |
| `ModelResponse` | `model.py` | Normalised reply from LiteLLM | model gateway | orchestrator |
| `ToolInvocation` | `tool.py` | Validated tool call emitted by the model | orchestrator | tool executor |
| `ToolResult` | `tool.py` | Tool execution outcome | tool executor | orchestrator |
| `RetrievalResult` | `retrieval.py` | RAG response (ranked chunks + metadata) | RAG pipeline (external) | retrieval client |
| `EvaluationRecord` | `evaluation.py` | Scored eval outcome (offline or online) | evaluator | eval dashboards |
| `TelemetryEvent` | `telemetry.py` | OTel-compatible span record | every service | Langfuse, Datadog |

All models use `ConfigDict(extra="forbid")` — extra fields are a contract violation, not a silent pass-through.

---

## Enums worth knowing

- `Intent` — `grounded_qa` · `extraction` · `tool_action` · `chitchat`
- `ModelTier` — `small` · `mid` · `frontier` (three-tier cascade, Section 19 D4)
- `OrchestratorPhase` — matches the Section 5 request lifecycle
- `ActivationStatus` — `active` · `canary` · `archived` · `draft`
- `ToolResultStatus` — `success` · `error` · `denied` · `timeout`
- `EvaluationType` — `offline_regression` · `online_sample` · `golden_run` · `safety_eval`

---

## JSON Schema export

```bash
uv run python scripts/export_schemas.py --out build/schemas
```

Writes one `<ContractName>.schema.json` per Pydantic model. The CI `contracts` job runs this on every PR and uploads the output as an artifact so downstream teams (RAG, frontend) can diff against their integration code.

---

## Changing a contract

1. Read Section 8 of the execution plan first.
2. Update the Pydantic model.
3. Update the example in `packages/contracts/tests/test_contracts_section_8.py` **and** the corresponding payload in Section 8 in the same PR.
4. `make check` must be green.
5. Downstream consumers (RAG pipeline, frontend) consume the regenerated JSON Schema — give them a heads-up if the change is breaking.
