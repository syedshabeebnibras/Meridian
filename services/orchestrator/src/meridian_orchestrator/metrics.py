"""Prometheus metrics for the orchestrator.

A dedicated CollectorRegistry is used (instead of the default global
prometheus_client.REGISTRY) so repeated imports inside pytest don't
raise "Duplicated timeseries" errors. The FastAPI /metrics handler
serializes this registry via generate_latest().

Metric conventions follow OpenMetrics naming:
  - `*_total` suffix for Counters
  - `*_seconds` suffix for durations
  - USD cost is a Counter, not a gauge, so Grafana can rate() it
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

REQUESTS_TOTAL = Counter(
    "meridian_requests_total",
    "Total /v1/chat requests served, labeled by terminal status.",
    labelnames=("status",),
    registry=REGISTRY,
)

REQUEST_DURATION_SECONDS = Histogram(
    "meridian_request_duration_seconds",
    "End-to-end /v1/chat wall-clock latency.",
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0),
)

COST_USD_TOTAL = Counter(
    "meridian_cost_usd_total",
    "Total LLM cost accounted (USD). Use rate() over this to see burn rate.",
    registry=REGISTRY,
)

RATE_LIMITED_TOTAL = Counter(
    "meridian_rate_limited_total",
    "Requests rejected at the edge by the per-user rate limiter.",
    registry=REGISTRY,
)

CIRCUIT_OPEN_TOTAL = Counter(
    "meridian_circuit_open_total",
    "Requests that short-circuited because the provider breaker was open.",
    registry=REGISTRY,
)


def render() -> bytes:
    """Serialize the registry in Prometheus text format."""
    return generate_latest(REGISTRY)
