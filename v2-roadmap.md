# Meridian v2 Roadmap

Drafted from **Section 30 Revised Timeline with Advanced Extensions**
of the execution plan. Every item has an explicit prerequisite on v1
stability — nothing on this roadmap ships before the 90-day report
signs off on v1.

The canonical ordering in Section 30 is by start-date relative to v1
launch. The **prerequisites** column is what actually gates each
extension, so the real schedule is a DAG — items with independent
prereqs can run in parallel.

---

## Section 30 dependency graph

```
                 v1 launch (Day 0)
                         │
         ┌───────────────┼───────────────────────────┐
         │               │                           │
   30 days of prod    eval pipeline            production feedback
   data + labels      (Phase 5)                data (Phase 8 feedback)
         │               │                           │
         ▼               ▼                           ▼
  §22 Fine-tuned   §28 Self-improving        §25 Online learning
  classifier       evals                     + RLHF-lite
  (+2 weeks)       (+2 weeks)                (+3 weeks)
         │
         ├─────────────────┬──────────────────────┐
         │                 │                      │
   45 days (needs          60 days (needs        90 days (needs §22
   prod feedback           production            fine-tuned classifier)
   pairs for reranker)     quality scores)       │
         │                 │                     │
         ▼                 ▼                     ▼
  §24 Custom         §23 Learned router  §27 Speculative execution
  reranker           (cost: -25-40%)     + adaptive latency
  (+3 weeks)         (+2 weeks)          (p50 latency: -40%)
                           │
                           └──────────┬─────────────┐
                                      │             │
                                      ▼             ▼
                                §26 Custom     §21 Agentic
                                embeddings     workflow engine
                                (+2 weeks)     (needs budget
                                               controls, +4 weeks)
                                                    │
                                                    ▼
                                              §29 Event-driven
                                              architecture
                                              (needs agentic scale,
                                              +4 weeks)
```

---

## Prioritized backlog

Priority is a mix of expected impact (Section 30 cumulative impact
table) and dependency depth (earlier items unblock more).

### Tier 1 — v1+30 to v1+60

| # | Section | Extension | Prereq | Duration | Expected impact |
|---|---|---|---|---|---|
| 1 | §22 | Fine-tuned domain classifier | 30 days prod data | 2 weeks | Cost: -30%; Latency: -250ms |
| 2 | §28 | Self-improving eval system | Langfuse traces, golden dataset | 2 weeks | Continuously expanding eval coverage |
| 3 | §25 | Online learning + RLHF-lite | Feedback collection pipeline | 3 weeks | Automated prompt optimization |

### Tier 2 — v1+45 to v1+90

| # | Section | Extension | Prereq | Duration | Expected impact |
|---|---|---|---|---|---|
| 4 | §24 | Custom domain reranker | Production feedback data | 3 weeks | NDCG@5 +10-25% |
| 5 | §23 | Learned model router | Quality scores per intent | 2 weeks | Cost -25-40% |
| 6 | §26 | Custom embedding model | Query-doc pairs from prod | 2 weeks | Retrieval recall +10-20% |

### Tier 3 — v1+90 to v1+120

| # | Section | Extension | Prereq | Duration | Expected impact |
|---|---|---|---|---|---|
| 7 | §27 | Speculative execution + adaptive latency | Fine-tuned classifier (§22) | 2 weeks | p50 -40% |
| 8 | §21 | Agentic workflow engine | Stable v1 + budget controls | 4 weeks | Handles complex multi-doc |

### Tier 4 — v1+120+

| # | Section | Extension | Prereq | Duration | Expected impact |
|---|---|---|---|---|---|
| 9 | §29 | Event-driven architecture | Agentic scale needs | 4 weeks | Async + independent scaling |

---

## Cumulative impact (Section 30)

| Metric | v1 baseline | After all extensions |
|---|---|---|
| Answer accuracy | 80% | 90%+ |
| p50 latency | 2.5 s | 1.2 s |
| p95 latency | 4.0 s | 3.0 s |
| Cost per request | $0.015 | $0.006 |
| Monthly cost (500 DAU) | $2,500 | $1,000 |
| Retrieval NDCG@5 | 0.70 | 0.85 |
| Unescalated queries | 75% | 90% |
| Injection resistance | 90% | 97%+ |

---

## v1 items not in Section 30

These are deferred features from Section 4 §Out of scope that are
candidates for v2 regardless of the advanced extensions:

- **Voice interface** — re-evaluate based on beta demand
- **Multi-tenant support** — only if Meridian expands beyond internal use
- **Cross-session memory** — Redis TTL in v1 is 1 hour; longer memory is a user-controlled preference
- **Real-time document sync to knowledge base** — still owned by Data Platform; coordinate but don't own

---

## How this roadmap gets updated

- Every month: re-rank tiers based on the 30/60/90-day reports.
- When a tier-1 item lands, its downstream dependencies open up.
- Anything that hits "blocked by missing data" for 30 days gets a
  data-collection spike before the main work kicks off.
- Updates to this file are tracked via git; mark supersession points
  with a "_(updated YYYY-MM-DD by [name])_" footer when you ship one.
