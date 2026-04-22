# Security Review Process

Section 9 of the execution plan is the canonical failure-mode analysis;
this doc is how we actually exercise it.

---

## When to run

- **Pre-launch** (Phase 7): full red-team exercise against staging. Zero
  P1 findings is an exit criterion.
- **Monthly** (Section 11 §Red-team review process): recurring internal
  exercise after launch.
- **On-demand**: when a new prompt version activates or a new tool
  integrates — run at minimum the injection + tool-misuse subset.

---

## Running the automated suite

```bash
uv run python scripts/red_team.py \
  --endpoint $STAGING_URL/v1/chat \
  --output ops/security-review-report.md
```

Exits non-zero if any P1 attack succeeds. The attack catalogue covers:

| Category | Section 9 mode | Count |
|---|---|---|
| Prompt injection | 5 (direct) | 3 |
| PII extraction | 7 | 2 |
| Tool misuse | 3 | 2 |
| Out-of-scope refusal | Section 10 refusal gate | 1 |

---

## Manual review

The automated suite is a floor, not a ceiling. For each quarterly review,
at least one Security engineer + one AI engineer should spend two hours
trying attacks not in the catalogue:

1. Inspect the prompts/*.yaml in the active prompt registry — look for
   new surfaces (a new `{{ variable }}` is an injection vector).
2. Inspect every tool schema in `services/tool-executor/src/meridian_tool_executor/tools/`
   — new parameters need the same escaping story as existing ones.
3. Attempt indirect injection by crafting a query that would require the
   RAG pipeline to return a poisoned document. (Requires coordination
   with Data Platform to inject test fixtures into the index.)
4. Stress guardrail thresholds: can you get Llama Guard to flag benign
   queries? Can you slip malicious content past it?

Document any successful attacks in `ops/security-review-report.md` with
reproduction steps + the severity assessment.

---

## Adding a new attack to the catalogue

Append to the `ALL_CASES` list in `scripts/red_team.py`:

```python
AttackCase(
    id="inj_new_variant",
    severity="P1",               # attack being *effective* is a launch blocker
    category="injection",
    query="<the exact prompt the attacker would send>",
    expected_blocked_or_refused=True,
    must_not_contain=["<forbidden substring in the reply>"],
    description="<one-line description>",
),
```

Every red-team finding that turned into a real issue should be backfilled
as a test case so future reviews catch it automatically (Section 10
§Golden dataset update cadence).
