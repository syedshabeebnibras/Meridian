# Runbook — Latency Spike

**Triggered by:** `02_latency_spike` · `09_cache_hit_drop`

## Symptoms

- p95 end-to-end latency > 8s for 10 minutes
- Mid-tier model dispatch latency climbing but error rate flat
- Cache hit rate dropped below 50% (was 70%+)
- Dashboards: `01_service_health`, `02_model_performance`, `09_provider_health`

## Diagnose (≤ 10 min)

1. Open **Service Health** — confirm the p95 spike.
2. Open **Model Performance** — is it `model_dispatch` latency? Or a different stage (retrieval, assembly)?
3. Check `09_provider_health`:
   - Is one provider slow? LiteLLM failover should route to the other.
   - Is the slow provider the one we're currently routing to?
4. Check cache hit rate. A drop from 70%+ usually means the prompt prefix became unstable — check `prompt_audit_log` for a recent prompt activation.
5. Run `make regression` on the current prompts + hold the stub timings alongside the live numbers. If offline is fast and live is slow, it's infra.

## Remediate

**Provider slow:**
- Manually nudge LiteLLM to prefer the faster provider by swapping `priority: 1` in `infra/litellm/config.yaml`.
- `docker compose up -d litellm` reloads without downtime.

**Cache degradation:**
- Cache hit rate drops when the prompt prefix changes. Usually a prompt activation changed the stable portion (e.g. updated system prompt).
- If the prompt change is intentional, accept 24–48h of elevated latency while the cache warms.
- If unintentional, rollback the prompt.

**Assembly/retrieval slow:**
- Assembly over 1s indicates a Jinja loop bug or huge retrieved-doc list. Look at `meridian.prompt.total_tokens_assembled` — if it's near the budget, the template is consuming time on truncation passes.
- Retrieval over 2s is a Data Platform problem; escalate.

**System overload:**
- If the orchestrator itself is CPU-bound, scale out K8s replicas. Orchestration is stateless (Section 7) so horizontal scaling is safe.

## Rollback procedure

- Prompt rollback (same procedure as faithfulness).
- Model downgrade: temporarily pin every route to mid-tier via a config knob (`OrchestratorConfig.upgrade_threshold = 0.99` effectively disables upgrades).
- Revert the most recent Meridian deploy if timing correlates.

## Post-incident

- Add a latency-regression test to CI: the Phase 3 `test_p95_latency_under_four_seconds` is the template.
- If a prompt change caused persistent cache-miss: update `PROMPTS.md` to call out the cache-prefix stability requirement.
