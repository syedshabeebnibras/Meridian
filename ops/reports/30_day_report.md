# 30-Day Production Report — Meridian v1

Section 18 §First 30 days cadence. Published on day 30 of the 100%
rollout. One of three quarterly reports.

**Report period:** [YYYY-MM-DD] — [YYYY-MM-DD]
**Prepared by:** [AI Architect + Platform Engineer]

---

## 1. Executive summary

Three-sentence "what happened" for leadership. If the system is stable
and KPIs are green, say so plainly. If a launch gate slipped, lead with
that.

---

## 2. KPI scorecard

| KPI | Target (Section 1) | Day-30 actual | Status |
|---|---|---|---|
| User-reported answer accuracy | ≥ 80% | _ | |
| Cache hit rate | ≥ 70% | _ | |
| Hallucination rate | < 5% | _ | |
| p95 latency | < 4 s | _ | |
| PII leakage incidents | 0 | _ | |
| NPS (internal beta) | positive within 30 days | _ | |
| Monthly spend | < $12K at 500 DAU | _ | |

Pull each number from the listed dashboard; cite the query if you had
to derive it manually.

---

## 3. Stability

- Total P1 incidents: _
- Total P2 incidents: _
- Longest outage: _
- Rollback events (prompt or feature flag): _

Link each incident to its `ops/runbooks/_post_incident_template.md`
write-up.

---

## 4. Quality trends

Show the daily faithfulness + relevance averages over the 30-day
window. Call out any dip > 0.05 from the 7-day baseline and explain
the root cause.

## 5. Guardrail activity

| Guardrail | Triggers | False-positive rate | Action |
|---|---|---|---|
| LlamaGuard input | _ | _ | |
| Regex PII input | _ | _ | |
| Regex PII output | _ | _ | |
| Patronus Lynx output | _ | _ | |

If any FP rate > 5% (Section 10 exit gate), open a tuning ticket and
note it here.

## 6. Cost analysis

- Total spend: $_ (target ≤ $12K)
- Avg cost per request: $_
- Frontier model share: _% (target ≤ 10%)
- Top 5 most-expensive intent patterns: _

If spend trajectory would breach budget by day 60, flag it now.

## 7. User feedback

- Thumbs-up count: _
- Thumbs-down count: _
- Top 5 themes from negative feedback: _
- Top 5 positive themes: _

## 8. Prompt iterations

| Template | Version | Activated on | Regression pass-rate | Online faithfulness |
|---|---|---|---|---|
| classifier | v1 → v2 | | | |
| grounded_qa | v1 → v2 | | | |
| extraction | — | | | |
| tool_invocation | — | | | |

## 9. Golden dataset growth

- Dataset size at day 0: 125 (target)
- Dataset size at day 30: _
- Cases added from production failures: _
- Cases deleted as stale: _

Run `scripts/promote_to_golden.py` weekly; expect ~20 candidates over
30 days (Section 10 cadence: 10 every 2 weeks).

## 10. Action items for Days 30–60

- [ ] _
- [ ] _
- [ ] _

---

**Sign-off:**

| Role | Name | Approved? |
|---|---|---|
| AI Architect | | |
| Platform Lead | | |
| Security Engineer | | |
| PM | | |
