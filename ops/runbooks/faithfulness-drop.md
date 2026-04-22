# Runbook — Faithfulness Drop

**Triggered by:** `04_faithfulness_drop` · `08_regression_failure` · `10_zero_retrieval_spike`

## Symptoms

- Online `eval_results.scores.faithfulness` average < 0.8 over a 1-hour rolling window
- Nightly regression pass rate < 90%
- Users reporting incorrect / hallucinated answers
- Dashboards: `04_eval_quality_trends`, `06_prompt_versions`, `07_retrieval_quality`

## Diagnose (≤ 15 min)

1. Open **Eval Quality Trends** — confirm the drop is real and not a one-hour blip.
2. Open **Prompt Version Performance** — which prompt version owns the traffic during the drop window? Was a new version activated recently?
3. Check `prompt_audit_log`:
   ```sql
   SELECT * FROM prompt_audit_log
   WHERE created_at > now() - interval '24 hours'
   ORDER BY created_at DESC;
   ```
4. Check **Retrieval Quality** — zero-result rate or avg relevance score spike correlates with faithfulness drops. If retrieval is the culprit, the fix is upstream (Data Platform team).
5. Pull the 10 lowest-scoring eval traces from the last hour:
   ```sql
   SELECT * FROM eval_results
   WHERE eval_type='online_sample' AND scores->>'faithfulness' IS NOT NULL
   ORDER BY (scores->>'faithfulness')::float ASC
   LIMIT 10;
   ```
6. Read 3 of those traces end-to-end in Langfuse. Classify: retrieval problem, prompt problem, or model drift?

## Remediate

**Prompt regression (most common):**
```python
from meridian_prompt_registry import PromptRegistry
registry.rollback("grounded_qa", environment="prod", actor=you, reason="faithfulness drop from <score>")
```
Instant — takes effect on the next request (30s cache window).

**Retrieval problem:** escalate to Data Platform on-call. Meridian can't fix upstream RAG issues.

**Model drift:** if a provider has silently updated a model (Section 9 failure mode 12), pin to a specific version in `infra/litellm/config.yaml`.

## Rollback procedure

- Prompt rollback: see above; no deploy needed.
- Code rollback: revert the orchestrator commit if the drop correlates with a Meridian deploy.
- Model pin: edit `infra/litellm/config.yaml`, `docker compose up -d litellm`.

## Post-incident

- Add the failure case to the adversarial + golden datasets.
- If a prompt change caused it, write a regression test that catches it before merge.
- Section 10 post-incident requirement: RCA + test case added to golden dataset within 48 hours.
