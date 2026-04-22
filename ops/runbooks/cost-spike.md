# Runbook — Cost Spike

**Triggered by:** `07_daily_cost_overrun`

## Symptoms

- Daily spend > 150% of daily budget (~$400/day when budget is $12K/month)
- Per-request cost climbing above $0.05
- Frontier-tier usage share > 20%
- Dashboards: `03_cost_accounting`

## Diagnose (≤ 10 min)

1. Open **Cost Accounting** dashboard. Identify the spike's timing.
2. Break down by `meridian.model_tier`: is it frontier-share climbing, per-request tokens climbing, or request volume climbing?
3. Check `audit_log` for recent prompt changes — a longer system prompt or expanded retrieval budget increases per-request cost.
4. Look for runaway users in **User Engagement**: any single user issuing 100x normal volume?

## Remediate

**Frontier-tier abuse:**
- The `CostCircuitBreaker` auto-opens at 150% spend — verify it's engaged and degrading frontier requests to mid.
- If the breaker hasn't fired, check its configuration: `CostCircuitBreaker(daily_budget_usd=...)`.

**Retrieval budget bloat:**
- Token budget lives in each prompt YAML (`prompt_templates.token_budget`). A recent prompt version may have expanded `retrieval` from 6000 → 10000.
- Rollback the prompt or ship a v+1 with the tighter budget.

**Runaway user:**
- Engage `TokenBucketRateLimiter` for that user at a tighter rate.
- Contact the user's manager if automated queries are suspected.

**Model drift (same query, more tokens):**
- Pin the model version (Section 9 failure mode 12).

## Rollback procedure

- Prompt rollback (see faithfulness-drop runbook) immediately reduces the per-request token floor if the cause was prompt bloat.
- Cost circuit breaker resets at midnight UTC automatically.

## Post-incident

- If the spike persisted > 4 hours, engineering leadership gets paged — Section 7 Cost controls: "Runaway detection: alert on requests exceeding 2x expected cost".
- Tighten the `cost_per_req` alert threshold if normal spend was masking the anomaly.
- Update `default_rates()` in `packages/cost-accounting/src/meridian_cost_accounting/accountant.py` if provider pricing changed (don't let stale rates mask a real overrun).
