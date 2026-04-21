# Regression Suite

The regression suite validates a prompt template against a labeled dataset before any activation. It runs two modes:

| Mode | Client | Used for |
|---|---|---|
| **offline** | `StubModelClient` (canned responses) | CI gate — no API keys required |
| **live** | `LiteLLMClient` | Real accuracy/faithfulness measurement against the gateway |

Phase 2 exit criteria:
- Classifier accuracy ≥ 80% (50-example dataset target)
- Q&A faithfulness ≥ 0.75 (30-example dataset target)
- Regression suite running in CI ✓

---

## Running

```bash
# Offline (CI-safe) — every example needs a `stub_response` in the YAML.
uv run python -m meridian_evaluator.cli \
    --dataset datasets/classifier_v1.yaml \
    --client stub --registry file

# Live — hits LiteLLM. Requires `make up` + real API keys in `.env`.
uv run python -m meridian_evaluator.cli \
    --dataset datasets/grounded_qa_v1.yaml \
    --client live --registry postgres --env dev \
    --json-out /tmp/qa-result.json
```

The CLI exits non-zero when `pass_rate` drops below the exit-criteria threshold:
- classifier → 0.80
- grounded_qa → 0.75

---

## Dataset format

Datasets are YAML under `datasets/`. Two task types are supported in Phase 2.

### Classifier

```yaml
dataset_name: classifier_v1
task_type: classifier
prompt_name: classifier   # looked up in the registry (or prompts/ in file mode)

examples:
  - input: "What is the escalation procedure for a P1 database outage?"
    expected_intent: grounded_qa        # from meridian_contracts.Intent
    expected_tier: mid                  # optional — ModelTier
    stub_response:                      # optional — required for --client stub
      content: { intent: grounded_qa, confidence: 0.95, model_tier: mid }
      latency_ms: 100
```

Accuracy = exact-match on intent (with tier bonus when provided).

### Grounded Q&A

```yaml
dataset_name: grounded_qa_v1
task_type: grounded_qa
prompt_name: grounded_qa
system_vars:
  company_name: Acme

examples:
  - input: "What's the SLA for Enterprise customers?"
    retrieved_docs:                     # fixtures substituting for RAG
      - title: "Enterprise SLA 2026"
        url: "https://wiki.example.com/sla"
        content: "The Enterprise tier commits to 99.95% uptime..."
        relevance: 0.97
    golden_answer: "99.95% monthly uptime..."
    expected_citations:                 # source titles that MUST be cited
      - "Enterprise SLA 2026"
    stub_response:
      content: { ...grounded_qa_response payload... }
```

Faithfulness (Phase 2 provisional judge):
- Must cite every title in `expected_citations` (coverage ≥ 0.75)
- Must not cite a title missing from `retrieved_docs` (hallucination = fail)
- Must not refuse when `golden_answer` is non-empty

The real LLM-judge with human-calibrated kappa > 0.6 lands in Phase 5 (Section 10).

---

## Growing the datasets

Phase 2 ships seed sizes (classifier: 12, grounded_qa: 7). The Section-12 targets are 50 and 30. To expand:

1. Pull real queries from production logs once the system ships.
2. Have an SME label the intent / write the golden answer.
3. Append to the relevant YAML.
4. Run offline regression → verify the harness still passes.
5. Run live regression → confirm the exit-criteria thresholds still hold.

Adversarial / faithfulness-critical / extraction / tool-invocation datasets (Section 6) are Phase 4+ deliverables.
