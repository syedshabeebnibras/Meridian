# Runbook — Provider Outage

**Triggered by:** `01_high_error_rate` · `03_provider_circuit_open`

## Symptoms

- Error rate > 5% for 5 minutes
- Circuit breaker for a provider transitions to `open`
- Latency p95 climbs on a specific `gen_ai.system` dimension while others stay flat
- Dashboards: `01_service_health`, `09_provider_health`

## Diagnose (≤ 5 min)

1. Open **Meridian Service Health** dashboard — confirm elevated error rate.
2. Open **Provider Health** dashboard — is one provider spiking while others are flat?
3. Check provider status pages: status.anthropic.com · status.openai.com · status.azure.com.
4. `SELECT * FROM audit_log WHERE event_type='model_dispatch' AND status='error' ORDER BY created_at DESC LIMIT 50;` — look for a consistent error code (429, 502, 503).
5. Confirm LiteLLM failover is routing to the secondary — expected: `gen_ai.system` dimension shifts from primary to secondary on new requests.

## Remediate

- **If primary provider is confirmed down:** do nothing — Section 7 failover should route to secondary automatically. Verify traffic shifted and secondary is healthy.
- **If failover is NOT happening:** check LiteLLM config `litellm_settings.fallbacks`; the Meridian-side retry layer respects it. `docker compose restart litellm` if config reloaded.
- **If every provider is down:** the orchestrator returns `OrchestratorStatus.DEGRADED` with a "temporarily unavailable" message — users see a graceful failure, not a 500.
- **If error rate stays elevated after 15 min** with no provider correlation: suspect Meridian — pivot to the Latency Spike runbook.

## Rollback procedure

Provider outages don't require a code rollback. If a recent Meridian deploy correlates with the error spike:

```bash
# Inspect the most recent orchestrator deploy
gh api repos/syedshabeebnibras/Meridian/deployments --jq '.[0]'

# If needed, roll back by redeploying the previous commit
git checkout <previous-good-sha>
# ... team deploy procedure
```

## Post-incident

- Update `ops/runbooks/provider-outage.md` with anything that diverged from the steps above.
- Add a test case to the shadow suite that replays the failure signature.
- Consider adding the failed provider error code to `silence_list` so the alert doesn't re-fire on a known-bad combination.
