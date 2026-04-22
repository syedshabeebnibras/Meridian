# Security Review Report — Template

Fill this in after every red-team exercise. `scripts/red_team.py`
populates the attack table automatically with `--output` — the narrative
sections are on the reviewer.

---

## Summary

- **Review date:**
- **Reviewer(s):**
- **Staging endpoint:**
- **Section 9 failure modes covered:** 5 (injection), 6 (indirect injection), 7 (PII), 3 (tool misuse)
- **P1 findings:** <count>
- **P2 findings:** <count>
- **P3 findings:** <count>

**Launch recommendation:** PROCEED / BLOCK / CONDITIONAL

---

## Attacks

(`scripts/red_team.py --output` appends the table below.)

| # | ID | Severity | Attacker won? | Rationale |
|---|---|---|---|---|
| … | … | … | … | … |

---

## Findings

### P1

(If any: describe each finding, reproduction steps, and remediation. No P1
findings is the Section-12 Phase 7 exit criterion.)

### P2

### P3

---

## Remediation tracking

| Finding | Owner | Fix commit / PR | Deployed |
|---|---|---|---|
| | | | |

---

## Sign-off

| Role | Name | Date |
|---|---|---|
| AI Architect | | |
| Security Engineer | | |
| Tech Lead | | |
