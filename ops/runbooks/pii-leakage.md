# Runbook — PII Leakage / Safety Incident

**Triggered by:** `05_pii_leakage` · `06_injection_spike`

**Severity: P1** — this is a compliance-adjacent incident. Declare an incident channel before any other action.

## Symptoms

- `RegexPIIOutputGuardrail` reports `BLOCK` with `leaked_count > 0`
- `LlamaGuardInputGuardrail` shows a spike in `injection` categories
- Langfuse trace has `output_guardrail.decision="block"` with PII details
- User report or legal escalation about an inappropriate response

## Diagnose (≤ 5 min)

1. **Declare an incident** in #sev-meridian (Slack). Silence takes longer than declaration — start the clock.
2. Open the specific trace in Langfuse using the alert's `trace_id`.
3. Record what PII leaked (entity type + count — NEVER copy raw PII into the incident channel).
4. Check `audit_log`:
   ```sql
   SELECT * FROM audit_log
   WHERE request_id = '<trace_id>'
   ORDER BY created_at;
   ```
5. Determine: was the PII in the user input (input PII echoed back) or fabricated by the model?

## Remediate

**Model fabricated PII (worst case):**
- Activate a stricter `output_guardrails` config immediately: require Patronus Lynx + regex PII; drop `min_score` for faithfulness to 0.9.
- Rollback the currently-active prompt version if it was recently deployed.
- Write an adversarial test case that reproduces the leak, add it to `datasets/pii_v1.yaml`.

**Input PII reflected:**
- Less severe, but still a problem. Confirm `RegexPIIInputGuardrail` is in the pipeline. If it is, the pattern list may need extension for the entity type that slipped through.

**Injection spike:**
- Check if it's a targeted attack (single user, specific IPs) vs. broad. If targeted: coordinate with Security to block the actor upstream.
- Tighten `LlamaGuardInputGuardrail.block_threshold` temporarily (e.g. 0.3 → 0.2) and measure FP rate.

## Rollback procedure

- Prompt rollback is usually the fastest remediation (see faithfulness-drop runbook).
- Disable the destructive tool(s) via `ToolRegistry` config if a tool misuse was involved.

## Post-incident

- **Legal/compliance escalation** within 4 hours for any confirmed PII leak.
- Monthly red-team review process (Section 11) should absorb the attack signature — update `datasets/adversarial_v1.yaml`.
- RCA writeup within 48 hours with explicit timeline, detection, and preventive steps.
