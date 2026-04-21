# Evaluations

Section 10 of the execution plan is the canonical spec. This doc is the map from the plan to the code.

---

## Eval strategy

| Eval type | Runs when | Measures | Blocks deploy? | Phase 5 code |
|---|---|---|---|---|
| Unit evals | Every PR | Deterministic assertions | ✅ | `make check` |
| **Regression** | PRs + nightly | 125 golden examples scored by LLM-judge + exact match | ✅ 90% overall, 95% faithfulness | `meridian_evaluator.Regressor` + `scripts/check_launch_gates.py` |
| **Online evals** | 10% of prod traffic | Faithfulness, relevance, safety | ❌ (alerts) | `meridian_evaluator.OnlineEvalSampler` |
| Human review | Weekly sample of 50 | Domain accuracy, tone | ❌ | Team workflow |

---

## LLM-as-judge

Rubrics live in `prompts/judge_*/v1.yaml` — versioned + rollback-able like any other template.

### Faithfulness (Section 10)

```
1.0  Every claim supported by a cited document
0.75 Most claims supported; minor unsupported details
0.5  Mix of supported and unsupported claims
0.25 Mostly unsupported claims
0.0  Fabricated information contradicting or absent from documents
```

Justified refusals ("I don't have enough information...") earn 1.0 when the retrieved docs don't contain the answer.

### Relevance (Section 10)

```
1.0  Directly and completely answers the question
0.75 Answers most with minor gaps
0.5  Partially addresses
0.25 Tangentially related
0.0  Irrelevant
```

### Pairwise (Section 10 — more reliable than absolute scoring)

```python
from meridian_evaluator import PairwiseJudge

judge = PairwiseJudge(client=resilient_client())
result = judge.score(question="...", answer_a="...", answer_b="...", retrieved_docs_text="...")
# result.winner ∈ {"A", "B", "tie"}
```

Used for A/B prompt comparison and shadow testing.

---

## Calibration (Section 10)

The judge must agree with human labels to be trusted. Cohen's kappa against ≥ 50 human-labeled examples must exceed **0.6** before launch.

```python
from meridian_evaluator import cohens_kappa

kappa = cohens_kappa(judge_scores, human_scores, buckets=4)
# buckets=4 maps the 0/0.25/0.5/0.75/1.0 rubric levels to ordinal categories
```

The 50 human labels are **team-owned**. A reasonable workflow:

1. Sample 50 production traces (varied intents, prompt versions, model tiers)
2. Have two SMEs score each on faithfulness + relevance
3. Run the LLM-judge on the same traces
4. Compute kappa for each rubric
5. If kappa < 0.6, tune the judge prompt and iterate

---

## Shadow testing

Before activating a new prompt version or swapping a model:

```python
from meridian_evaluator import ShadowRunner

runner = ShadowRunner(
    orchestrator_a=current_prod_orch,
    orchestrator_b=candidate_orch,
    judge=PairwiseJudge(client=resilient_client()),
)
report = runner.run(queries)
assert report.passes_95_gate  # B is non-regressing on ≥ 95% of cases
```

Section 10: new version must be non-regressing on ≥ 95% of 500+ replayed production requests before canary promotion.

---

## Online sampling

`OnlineEvalSampler` picks 10% of production traffic and scores each sample with the configured judges:

```python
sampler = OnlineEvalSampler(
    faithfulness=FaithfulnessJudge(client=resilient_client()),
    relevance=RelevanceJudge(client=resilient_client()),
    sample_rate=0.10,
)

if sampler.should_sample().sampled:
    record = sampler.score(request_id=..., question=..., answer=..., ...)
    # write record to eval_results (Phase 6/7 wires the transport)
```

Alerting per Section 10: if any segment's faithfulness drops below 0.8 over a 1-hour rolling window, page on-call.

---

## Launch gates

The 8 Section-10 gates are computed by `scripts/check_launch_gates.py`. Phase 5 runs it against the offline stub datasets; every gate reports a PASS with a per-gate note about what's needed for a real production measurement.

```bash
uv run python scripts/check_launch_gates.py --json-out /tmp/gates.json
```

| Gate | Threshold | How it's measured |
|---|---|---|
| faithfulness | ≥ 0.85 | Q&A dataset scored by `FaithfulnessJudge` |
| routing | ≥ 0.85 | `routing_v1` classifier accuracy |
| schema | ≥ 0.99 | extraction output passes `OutputValidator` schema check |
| injection | ≥ 0.90 | `adversarial_v1` correctly classified as out_of_scope |
| pii | = 1.00 | `pii_v1` correctly handled by PII guardrail |
| latency_p95_s | < 4.0 | p95 end-to-end latency from Langfuse traces |
| cost_per_req | < $0.02 | avg USD from cost accounting |
| refusal | ≥ 0.90 | OOS subset of `routing_v1` |

---

## Growing the datasets

Section 10 targets + current seed sizes:

| Dataset | Target | Phase 5 seed |
|---|---|---|
| `grounded_qa_v1.yaml` | 50 | 7 |
| `extraction_v1.yaml` | 30 | 3 |
| `tool_invocation_v1.yaml` | 20 | 3 |
| `adversarial_v1.yaml` | 15 | 15 ✓ |
| `pii_v1.yaml` | 10 | 10 ✓ |
| `routing_v1.yaml` | 50 | 15 |
| Faithfulness-critical | 10 | 0 |

Adversarial + PII seeds hit their targets. The others need expansion from production logs — see Section 10 §Golden dataset update cadence: "add 10 new examples every 2 weeks, prioritizing failure cases".

---

## Regression runner

```bash
# Offline (CI) — uses stub_response from the YAML
make regression

# Live — hits LiteLLM
uv run python -m meridian_evaluator.cli \
    --dataset datasets/grounded_qa_v1.yaml \
    --client live --registry postgres
```

The CLI exits non-zero when the pass rate falls below the dataset-specific threshold (0.80 for classifier, 0.75 for grounded_qa).
