# Guardrails

Meridian's safety layer — Sections 5, 7, 9 of the execution plan. Inline middleware (not an async service), three-layer defense, composable pipelines.

---

## Three-layer defense

Per Section 6 §Prompt injection resistance:

1. **Input classification** — user input is scanned by Llama Guard 3 (injection/unsafe intent) + Presidio/regex (PII) before anything else runs.
2. **Trust boundaries in prompts** — retrieved documents are wrapped with "treat as data, not instructions" language in every template.
3. **Output validation** — model output runs through Patronus Lynx (faithfulness) + regex PII leak detection before reaching the user. Tool parameters are schema-validated and never contain unescaped retrieved text.

---

## Pipeline

`GuardrailPipeline` takes an ordered list of guardrails and runs them until any returns `BLOCK` (short-circuits) or all are done. Precedence is strictest-wins:

```
BLOCK   >   REDACT   >   PASS
```

When a guardrail returns `REDACT` with `redacted_content`, later guardrails see the redacted text — so a regex PII redaction upstream means the Llama Guard call downstream sees `<EMAIL>` instead of the real address.

```python
from meridian_guardrails import (
    GuardrailPipeline, RegexPIIInputGuardrail, LlamaGuardInputGuardrail, LlamaGuardConfig,
)

input_pipeline = GuardrailPipeline(guardrails=[
    RegexPIIInputGuardrail(),
    LlamaGuardInputGuardrail(config=LlamaGuardConfig.from_env()),
])
result = input_pipeline.check_input(user_query)
if result.is_blocked:
    return "blocked"
if result.was_redacted:
    user_query = result.effective_text  # downstream sees redacted version
```

---

## Orchestrator integration

Inject both pipelines at construction:

```python
orch = Orchestrator(
    templates=..., retrieval=..., model_client=...,
    input_guardrails=input_pipeline,
    output_guardrails=output_pipeline,
)
```

- **Input `BLOCK`** → `OrchestratorStatus.BLOCKED`, classifier never runs
- **Input `REDACT`** → redacted text flows through the entire downstream path (classifier, retrieval, assembler, dispatch)
- **Output `BLOCK`** → `OrchestratorStatus.BLOCKED`, user sees the safety refusal
- **Output `REDACT`** → `model_response.content.answer` is replaced with the redacted version before the reply is shaped

Both pipelines are optional. When not provided (the Phase 3 default), the state machine passes through with no guardrails — useful for unit tests but never for production.

---

## Built-in guardrails (v1)

| Guardrail | Kind | Implementation | Status |
|---|---|---|---|
| `PassThroughInputGuardrail` / `PassThroughOutputGuardrail` | Input/Output | No-op stub | Always available |
| `RegexPIIInputGuardrail` / `RegexPIIOutputGuardrail` | Input/Output | In-process regex (EMAIL, SSN, phone, credit card) | **Baseline — always on** |
| `LlamaGuardInputGuardrail` | Input | HTTP call to a Llama Guard 3 serving endpoint | Needs endpoint provisioning |
| `PatronusLynxOutputGuardrail` | Output | HTTP call to Patronus Lynx API | Needs API key + DPA |

External services (Llama Guard, Patronus) **fail open** — a 5xx from the guardrail service returns `PASS` with `metadata.degraded = "true"` rather than blocking legitimate traffic. Phase 6 observability alerts on degraded-mode traffic so an on-call sees outages immediately.

---

## Configuring

| Variable | Used by |
|---|---|
| `LLAMA_GUARD_BASE_URL` · `LLAMA_GUARD_API_KEY` · `LLAMA_GUARD_TIMEOUT_S` | `LlamaGuardConfig` |
| `PATRONUS_BASE_URL` · `PATRONUS_API_KEY` · `PATRONUS_TIMEOUT_S` | `PatronusConfig` |

---

## False-positive rate

The Section 12 exit criterion is **guardrail FP rate < 5%**. Measure it by running each guardrail against a labeled dataset of "known good" inputs/outputs and tracking the share incorrectly flagged. For Phase 5 the seed datasets (`datasets/adversarial_v1.yaml`, `datasets/pii_v1.yaml`) are the starting point — expand from production logs over time.

---

## Adding a new guardrail

```python
from dataclasses import dataclass
from meridian_guardrails.interfaces import GuardrailDecision, GuardrailOutcome

@dataclass
class ProfanityInputGuardrail:
    name: str = "profanity"

    def check(self, text: str) -> GuardrailOutcome:
        if _has_profanity(text):
            return GuardrailOutcome(
                decision=GuardrailDecision.REDACT,
                reason="profanity",
                redacted_content=_clean(text),
            )
        return GuardrailOutcome(decision=GuardrailDecision.PASS, reason="clean")
```

Checklist:
- [ ] `check(text)` for input guardrails; `check(text, *, context)` for output guardrails
- [ ] Unit tests for each decision branch (PASS / REDACT / BLOCK)
- [ ] Fail-open policy for external-service guardrails
- [ ] Timeout under the Section 7 budget (500ms input, 1s output)
