# Post-Launch Optimization

Phase 9 of the execution plan — the ongoing cycle that takes a stable
v1 from "working" to "tuned." Everything here runs **after** the Phase 8
100% rollout sticks.

Section 18 defines three windows:
- **Days 0–30 Stabilize** — ship the cycle, don't optimize yet
- **Days 30–60 Optimize** — cost routing, cache hit-rate, prompt tuning
- **Days 60–90 Plan v2** — 90-day report, tech-debt paydown, v2 roadmap

---

## The weekly review (Section 11)

Every Monday, the team reviews the top 20 lowest-scoring traces from
the past week. `scripts/weekly_review.py` builds the document:

```bash
DATABASE_URL=postgresql+psycopg://... uv run python scripts/weekly_review.py \
    --output /tmp/weekly_$(date +%Y-%m-%d).md
```

Output includes:
- Pattern hypotheses — does one `(intent, prompt_version)` pair account for ≥ 4 of the 20?
- Per-trace drill-down with `request_id` so anyone can open it in Langfuse
- Suggested actions (prompt tuning, golden dataset promotion, guardrail retune)

If you're running against a Langfuse/eval-results dump (offline review):

```bash
uv run python scripts/weekly_review.py --from-jsonl dump.jsonl --output /tmp/weekly.md
```

### Action-item workflow

For every pattern surfaced:
1. Open 3 lowest-scoring traces in Langfuse, read end-to-end.
2. If a prompt-tuning ticket is warranted → assign to AI/Prompt Engineer.
3. If a guardrail FP is the cause → tune threshold, log in `tasks/lessons.md`.
4. If a retrieval issue → escalate to Data Platform.
5. Promote reproducible failures to the golden dataset via `promote_to_golden.py`.

---

## Semantic response cache (Section 5 three-layer cache, Section 9 mode 10)

`packages/semantic-cache` provides a pgvector-backed response cache with
a cosine similarity threshold of **0.95** (the Section 9 staleness-risk
line).

### Partition key

Queries are partitioned by a hash of the retrieved doc-id set. Two
users asking the same question against different retrieval sets get
different cache entries — so cache hits are always faithful to the
docs they were originally grounded in.

### Wiring

```python
from meridian_semantic_cache import PostgresSemanticCache
from meridian_contracts import ModelResponse

cache = PostgresSemanticCache(
    embedding_model=your_embedding_model,
    session_factory=session_factory,
)

# Inside the orchestrator hot path:
lookup = cache.lookup(query=user_query, partition_key=retrieved_ids_hash)
if isinstance(lookup, CacheHit):
    return lookup.response_content          # skip model dispatch entirely

# After a successful dispatch:
cache.store(
    query=user_query,
    partition_key=retrieved_ids_hash,
    response_content=model_response.content,
    metadata={"prompt_version": "grounded_qa_v3"},
)
```

### Tuning the threshold

Section 18 day-60 target is a **75% cache hit rate**. Levers:
- Raise TTL from 1h → 2h if staleness isn't a concern for a given intent
- Lower similarity threshold from 0.95 → 0.92 for non-safety-critical intents
- Tighten prompt prefix stability (Section 6) so identical queries produce
  identical cache keys

Measure before/after every knob change. Record in the 60-day report
under "Cost optimization experiments".

---

## Dataset expansion (Section 10 cadence)

```bash
DATABASE_URL=... uv run python scripts/promote_to_golden.py \
    --days 14 --limit 10 \
    --output datasets/golden_candidates.yaml
```

Generates up to 10 candidate rows from low-scoring traces with human
labels. SME workflow:
1. Open `datasets/golden_candidates.yaml`
2. For each candidate: fill in `golden_answer`, mark `reviewer_action="accept"` or `"reject"`
3. Move accepted rows into `datasets/grounded_qa_v1.yaml` (or the right task-type file)
4. Commit

Cadence: Section 10 calls for 10 new examples every 2 weeks. A stale
golden set quietly erodes eval quality — don't skip.

---

## Monthly red-team (Section 11)

Once per month:

```bash
STAGING_URL=... uv run python scripts/red_team.py \
    --output ops/security-review-report.md
```

Plus 2 hours of manual exploration following `SECURITY-REVIEW.md`.

Track attack success rate over time — the goal is **decreasing**. If
success rate plateaus or increases, that's a P2 in the 60-day report.

---

## The three reports

Under `ops/reports/`:

| File | When | Contents |
|---|---|---|
| `30_day_report.md` | Day 30 | KPI scorecard · stability · quality trends · initial cost analysis |
| `60_day_report.md` | Day 60 | Trend deltas · cost optimization experiments · prompt iterations · deferred v2 items |
| `90_day_report.md` | Day 90 | Full KPI scorecard · exit-criteria verification · tech-debt inventory · v2 roadmap pointer |

These are templates — each iteration fills in the blanks. Archive prior
iterations rather than overwriting; the trend across quarters is often
more useful than the single latest report.

---

## v2 planning

`v2-roadmap.md` is the living backlog, drafted from Section 30's
dependency graph. Update it:

- After every 30/60/90 report
- When a tier-1 item lands (unblocks downstream work)
- If a Section-30 extension's prerequisites change

---

## Cost optimization knobs (Section 18 day-60)

The levers, roughly in order of impact:

1. **Routing threshold** — `OrchestratorConfig.upgrade_threshold` (default 0.85). Raise toward 0.90 to push more traffic to mid-tier; measure faithfulness impact first.
2. **Frontier cap** — enforce via `CostCircuitBreaker`. Section 7 target: frontier share ≤ 10%.
3. **Cache hit rate** — see semantic cache tuning above.
4. **Prompt token budget** — tighten `retrieval` and `few_shot` slots if regression pass-rate is unaffected.
5. **Small-tier promotion** — if a specific intent shows faithfulness > 0.9 on small-tier shadow runs, lock it there.

Every change is an experiment — before/after on the same 50-query
benchmark, decision recorded in the 60-day report.

---

## Tech debt paydown (Section 18 day-60 → day-90)

Standing list (update per the 90-day report inventory):

- [ ] Remove any hardcoded prompt content — migrate to the registry
- [ ] Bring the `classifier_v1` dataset to the full 50-example target
- [ ] Bring the `grounded_qa_v1` dataset to the full 30-example target (+ 10 faithfulness-critical)
- [ ] Wire the OTel collector end-to-end to a live observability platform
- [ ] Replace `MockRetrievalClient` in prod — confirm Data Platform RAG endpoint is live
- [ ] Upgrade provider API versions as released (Section 9 mode 12)
