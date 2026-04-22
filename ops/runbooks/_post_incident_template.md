# Post-Incident Review Template

Use for any P1 or P2. Section 11 requires completion within 48 hours.

## Summary

- **Incident ID / timestamp range:**
- **Severity:** P1 / P2 / P3
- **Duration:**
- **Impact:** (users affected, requests blocked, data leaked, $ cost)
- **Detected by:** (alert name, user report, eval drop)

## Timeline

| Time (UTC) | Event |
|---|---|
| HH:MM | Alert fired / user reported / eval drop observed |
| HH:MM | On-call acknowledged |
| HH:MM | Diagnosis complete |
| HH:MM | Remediation deployed |
| HH:MM | Verified recovered |
| HH:MM | All clear |

## Root cause

Single root cause in one sentence, then a paragraph of detail.

## What went well

- Detection time
- Diagnosis speed
- Specific tools / runbooks / dashboards that helped

## What didn't

- Anything that slowed detection, diagnosis, or remediation.

## Action items

| Owner | Action | Due | Tracking |
|---|---|---|---|
| | Add regression test covering this case | | |
| | Update runbook with new signature | | |
| | Tighten alert threshold | | |
| | Add golden-dataset example | | |

## Links

- Langfuse trace(s):
- Commit(s) involved:
- Alert: `ops/alerts/alerts.yaml#<id>`
- Runbook used:
