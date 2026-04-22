# Operations

The Phase 6 observability + ops layer — Sections 9 and 11 of the execution plan.

---

## Telemetry

Every stage of the orchestrator emits a span through `meridian_telemetry.Tracer`. Spans are recorded as `RecordedSpan` objects and handed to a swappable `SpanExporter`:

| Exporter | Purpose |
|---|---|
| `NoOpExporter` | Default — zero overhead when telemetry is off |
| `InMemoryExporter` | Tests — captures spans for assertions |
| `OTelExporter` | Prod — bridges to `opentelemetry-sdk` |

Span names use the `LifecycleStage` enum so the dashboard queries can
reference them by constant. Build a Section-8 `TelemetryEvent` from a
recorded span with `build_telemetry_event()`.

```python
from meridian_telemetry import InMemoryExporter, LifecycleStage, Tracer

exporter = InMemoryExporter()
tracer = Tracer(service="meridian-orchestrator", exporter=exporter)

with tracer.span(LifecycleStage.MODEL_DISPATCH) as span:
    span.set_attributes({
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": "meridian-mid",
        "meridian.cost_usd": 0.012,
    })

# Later, export events to Langfuse / Datadog:
for recorded in exporter.spans:
    event = build_telemetry_event(recorded)
    # send `event` however you like
```

The orchestrator takes a `tracer=` argument; pass one in from the top of
your app to route everything through a single exporter.

---

## Cost accounting

`meridian_cost_accounting.CostAccountant` takes a `ModelResponse.usage`
and returns a `CostBreakdown` with per-section USD. Rate table ships with
the models in `infra/litellm/config.yaml`; update `default_rates()` if
provider pricing changes.

```python
from meridian_cost_accounting import CostAccountant, PerUserDailyTracker, CostCircuitBreaker
from decimal import Decimal

accountant = CostAccountant()
tracker = PerUserDailyTracker()
breaker = CostCircuitBreaker(daily_budget_usd=Decimal("400"))  # $12K/month / 30 days

breakdown = accountant.cost_of(model_response)
tracker.record(user_id, breakdown.total_usd)
breaker.record(breakdown.total_usd)

# Before dispatching a frontier-tier request:
breaker.check_frontier_allowed()   # raises CostBreakerOpenError if spend > 150% budget
```

Wire into the orchestrator via the constructor:

```python
Orchestrator(
    ...,
    cost_accountant=CostAccountant(),
    user_spend_tracker=PerUserDailyTracker(),
)
```

The `OrchestratorReply.cost_usd` field is populated on every successful
request.

---

## Session memory

```python
from meridian_session_store import InMemorySessionStore, RedisSessionStore
from redis import Redis

# Dev:
session_store = InMemorySessionStore(ttl_seconds=3600)

# Prod:
session_store = RedisSessionStore(redis_client=Redis.from_url(REDIS_URL))

# Hydrate a UserRequest's conversation_history from the store:
turns = session_store.get(user_request.session_id)
```

Phase 7 wires the store into `Orchestrator.handle()` automatically when the
request arrives with an empty `conversation_history`.

---

## Rate limiting + error taxonomy

```python
from meridian_ops import TokenBucketRateLimiter, MeridianError, ProviderRateLimitedError

limiter = TokenBucketRateLimiter(capacity=30, refill_per_second=1.0)

try:
    limiter.allow(user_request.user_id)
except RateLimitExceededError:
    # Return a friendly "slow down" response
    ...
```

Every orchestrator failure raises a typed subclass of `MeridianError` with
an `MERIDIAN-###` code (Section 11 §Error taxonomy). Use the code in
dashboards + alerts for precise grouping.

---

## Dashboards

Ten dashboards defined as vendor-neutral YAML under `ops/dashboards/`.
Import into Grafana, Datadog, or Langfuse — each file lists panels with
PromQL-style queries, units, and warn/crit thresholds.

| # | File | Audience |
|---|---|---|
| 1 | `01_service_health.yaml` | On-call, all engineers |
| 2 | `02_model_performance.yaml` | AI engineer, Platform |
| 3 | `03_cost_accounting.yaml` | Engineering leadership |
| 4 | `04_eval_quality_trends.yaml` | AI engineer, Tech lead |
| 5 | `05_guardrail_activity.yaml` | Security engineer |
| 6 | `06_prompt_versions.yaml` | AI/Prompt engineer |
| 7 | `07_retrieval_quality.yaml` | AI engineer, Data Platform |
| 8 | `08_user_engagement.yaml` | PM, Tech lead |
| 9 | `09_provider_health.yaml` | Platform, On-call |
| 10 | `10_incident_anomaly.yaml` | On-call, Tech lead |

---

## Alerts

Ten alerts in `ops/alerts/alerts.yaml`. Each has a condition, severity
(P1/P2/P3), action, and a pointer to the matching runbook.

| ID | Alert | Sev |
|---|---|---|
| 01 | High error rate | P1 |
| 02 | Latency spike | P2 |
| 03 | Provider circuit breaker open | P2 |
| 04 | Faithfulness score drop | P2 |
| 05 | PII leakage detected | P1 |
| 06 | Injection attempt spike | P3 |
| 07 | Daily cost overrun | P2 |
| 08 | Regression suite failure | P3 |
| 09 | Cache hit rate drop | P3 |
| 10 | Zero-result retrieval spike | P3 |

---

## Runbooks

Five runbooks for the top incident classes, plus a post-incident template.

| Runbook | Triggered by |
|---|---|
| `ops/runbooks/provider-outage.md` | Alert 01, 03 |
| `ops/runbooks/faithfulness-drop.md` | Alert 04, 08, 10 |
| `ops/runbooks/pii-leakage.md` | Alert 05, 06 |
| `ops/runbooks/cost-spike.md` | Alert 07 |
| `ops/runbooks/latency-spike.md` | Alert 02, 09 |
| `ops/runbooks/_post_incident_template.md` | Use for every P1/P2 within 48h |

Each runbook has: symptoms, ≤10 min diagnosis, remediation, rollback,
post-incident steps.

---

## Weekly production review (Section 11)

Every Monday:
- Top 20 lowest-scoring traces from the past week
- Guardrail trigger analysis (FP rate trend)
- Cost trend vs. budget
- User feedback themes
- Eval regressions
- Action items from previous week

This is the single highest-signal activity for improving Meridian quality
over time — don't skip it.

---

## Red-team review (Section 11)

Monthly internal red-team exercise:
- Security + AI engineer attempt injection, PII extraction, prompt manipulation
- Document all successful attacks; track success rate over time
- Update `datasets/adversarial_v1.yaml` and guardrail thresholds

---

## Team-owned deployment

- **Langfuse** — `docker-compose.yml` brings up the v3 stack for dev. Prod needs a persistent Postgres + Clickhouse + MinIO setup.
- **OTLP collector** — point `OTelExporter` at your target (Langfuse OTLP endpoint or a standalone collector).
- **Grafana / Datadog / PagerDuty** — import `ops/dashboards/*.yaml` and `ops/alerts/alerts.yaml`; wire alert channels to PagerDuty / Slack.
- **On-call rotation** — set up in PagerDuty; the runbooks are ready.
