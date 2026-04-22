"""Load test — Section 12 Phase 7 exit criterion: sustain 50 req/min.

Targets a Meridian staging endpoint with a configurable RPS for a
configurable duration, then reports success rate + latency percentiles.
Uses httpx + asyncio (no extra runtime dep like locust).

Usage:
  uv run python scripts/load_test.py \
      --endpoint https://meridian-orch.fly.dev/v1/chat \
      --rps 1.0 --duration 60 \
      --output /tmp/load_test.md
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

# A tiny corpus of realistic queries. Teams should expand this from
# datasets/*.yaml once Phase 7 is wired up.
DEFAULT_QUERIES = [
    "What is the escalation procedure for a P1 database outage?",
    "What are our SLA terms for the Enterprise tier?",
    "How long do we retain customer log data?",
    "Where do I find the on-call rotation schedule for next week?",
    "How do I request a new laptop?",
    "What's the format for a ticket ID?",
    "What's the hardware spec for engineers?",
    "How do I deploy a new microservice to staging?",
]


async def _run_one(
    client: httpx.AsyncClient, endpoint: str, query: str
) -> tuple[int, float, str | None]:
    payload: dict[str, Any] = {
        "request_id": f"req_load{uuid.uuid4().hex[:12]}",
        "user_id": f"load_u{random.randint(1, 100)}",
        "session_id": f"load_s{uuid.uuid4().hex[:8]}",
        "query": query,
        "conversation_history": [],
        "metadata": {"source": "load_test"},
    }
    started = time.perf_counter()
    try:
        response = await client.post(endpoint, json=payload, timeout=60.0)
        latency_ms = (time.perf_counter() - started) * 1000
        return response.status_code, latency_ms, None
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return 0, latency_ms, str(exc)


async def _load(endpoint: str, rps: float, duration_s: float) -> list[dict[str, Any]]:
    interval = 1.0 / rps if rps > 0 else 0
    results: list[dict[str, Any]] = []
    rng = random.Random(42)
    started = time.monotonic()
    tasks: list[asyncio.Task[tuple[int, float, str | None]]] = []

    async with httpx.AsyncClient() as client:
        next_fire = started
        while time.monotonic() - started < duration_s:
            now = time.monotonic()
            wait = max(0.0, next_fire - now)
            if wait:
                await asyncio.sleep(wait)
            query = rng.choice(DEFAULT_QUERIES)
            tasks.append(asyncio.create_task(_run_one(client, endpoint, query)))
            next_fire += interval

        # Drain.
        for task in tasks:
            status, latency_ms, err = await task
            results.append({"status_code": status, "latency_ms": latency_ms, "error": err})

    return results


def _render_report(results: list[dict[str, Any]], rps: float, duration_s: float) -> str:
    latencies = sorted(r["latency_ms"] for r in results if r["error"] is None)
    successes = [r for r in results if r["status_code"] == 200]
    errors = [r for r in results if r["error"] is not None or r["status_code"] >= 500]

    def _pctile(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    success_rate = (len(successes) / len(results)) if results else 0.0
    lines = [
        "# Load test report",
        "",
        f"- Target rate: {rps:.2f} req/s ({rps * 60:.0f} req/min)",
        f"- Duration: {duration_s:.0f}s",
        f"- Total requests: {len(results)}",
        f"- 2xx: {len(successes)} ({success_rate:.1%})",
        f"- Errors: {len(errors)}",
        "",
        "## Latency (ms)",
        "",
        f"- p50: {_pctile(0.50):.0f}",
        f"- p95: {_pctile(0.95):.0f}   ← Section-12 gate: < 4000",
        f"- p99: {_pctile(0.99):.0f}",
        "",
        "## Section 12 exit criteria",
        "",
        f"- 50 req/min sustained: {'PASS' if (rps * 60) >= 50 and success_rate >= 0.95 else 'FAIL'}",
        f"- p95 < 4s: {'PASS' if _pctile(0.95) < 4000 else 'FAIL'}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument(
        "--rps", type=float, default=1.0, help="Target requests per second (50 req/min = 0.83/s)"
    )
    parser.add_argument("--duration", type=float, default=60.0, help="Seconds to run for")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    results = asyncio.run(_load(args.endpoint, args.rps, args.duration))
    report = _render_report(results, args.rps, args.duration)
    print(report)
    if args.output:
        args.output.write_text(report)

    latencies = sorted(r["latency_ms"] for r in results if r["error"] is None)
    if not latencies:
        print("FAIL: no successful requests", file=sys.stderr)
        return 1
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    successes = [r for r in results if r["status_code"] == 200]
    if p95 >= 4000 or (len(successes) / len(results)) < 0.95:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
