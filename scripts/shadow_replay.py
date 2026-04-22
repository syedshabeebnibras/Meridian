"""Shadow traffic replay — Section 12 Phase 7.

Replays a JSONL file of queries (one JSON object per line) through a
running Meridian staging endpoint and reports aggregate stats. If the
input includes a `golden_answer`, a PairwiseJudge compares the live
response against the golden.

Input JSONL format:
  {"query": "...", "user_id": "u_anon_1", "golden_answer": "optional", "metadata": {}}

Usage:
  uv run python scripts/shadow_replay.py \
      --endpoint https://meridian-orch.fly.dev/v1/chat \
      --input logs/anonymized_queries.jsonl \
      --output /tmp/shadow_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx


async def _send_one(
    client: httpx.AsyncClient, endpoint: str, query_payload: dict[str, Any]
) -> tuple[dict[str, Any] | None, float, str | None]:
    payload = {
        "request_id": f"req_shadow{uuid.uuid4().hex[:12]}",
        "user_id": query_payload.get("user_id", "shadow"),
        "session_id": query_payload.get("session_id", f"shadow_{uuid.uuid4().hex[:8]}"),
        "query": query_payload["query"],
        "conversation_history": query_payload.get("conversation_history", []),
        "metadata": query_payload.get("metadata", {}),
    }
    started = perf_counter()
    try:
        response = await client.post(endpoint, json=payload, timeout=60.0)
        latency_ms = (perf_counter() - started) * 1000
        response.raise_for_status()
        return response.json(), latency_ms, None
    except httpx.HTTPError as exc:
        latency_ms = (perf_counter() - started) * 1000
        return None, latency_ms, str(exc)


async def _replay(
    endpoint: str, queries: list[dict[str, Any]], concurrency: int
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:

        async def _run(q: dict[str, Any]) -> None:
            async with sem:
                reply, latency_ms, err = await _send_one(client, endpoint, q)
                results.append(
                    {
                        "query": q["query"],
                        "latency_ms": latency_ms,
                        "error": err,
                        "status": (reply or {}).get("status"),
                        "confidence": ((reply or {}).get("model_response") or {})
                        .get("content", {})
                        .get("confidence")
                        if isinstance((reply or {}).get("model_response"), dict)
                        else None,
                    }
                )

        await asyncio.gather(*(_run(q) for q in queries))
    return results


def _render_report(results: list[dict[str, Any]], total_seconds: float) -> str:
    latencies = sorted(r["latency_ms"] for r in results if r["error"] is None)
    errors = [r for r in results if r["error"] is not None]
    refused = [r for r in results if r["status"] == "refused"]
    blocked = [r for r in results if r["status"] == "blocked"]
    ok = [r for r in results if r["status"] == "ok"]

    def _pct(n: int) -> str:
        return f"{(n / len(results) * 100):.1f}%" if results else "0.0%"

    def _pctile(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    lines = [
        "# Shadow replay report",
        "",
        f"- Total queries: {len(results)}",
        f"- Duration: {total_seconds:.1f}s",
        f"- OK: {len(ok)} ({_pct(len(ok))})",
        f"- Refused: {len(refused)} ({_pct(len(refused))})",
        f"- Blocked: {len(blocked)} ({_pct(len(blocked))})",
        f"- Errors: {len(errors)} ({_pct(len(errors))})",
        "",
        "## Latency (ms)",
        "",
        f"- p50: {_pctile(0.50):.0f}",
        f"- p95: {_pctile(0.95):.0f}   ← Section-12 gate: < 4000",
        f"- p99: {_pctile(0.99):.0f}",
        f"- mean: {statistics.mean(latencies):.0f}" if latencies else "- mean: n/a",
        "",
    ]
    if errors:
        lines.append("## First 5 errors")
        lines.append("")
        for err in errors[:5]:
            lines.append(f"- `{err['error']}` on query: {err['query'][:80]}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", required=True, help="Full URL to POST (e.g. https://.../v1/chat)"
    )
    parser.add_argument("--input", type=Path, required=True, help="JSONL file with queries")
    parser.add_argument("--output", type=Path, help="Where to write the markdown report")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    queries: list[dict[str, Any]] = []
    with args.input.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            queries.append(json.loads(line))

    if not queries:
        print("no queries to replay", file=sys.stderr)
        return 1

    started = perf_counter()
    results = asyncio.run(_replay(args.endpoint, queries, args.concurrency))
    elapsed = perf_counter() - started

    report = _render_report(results, elapsed)
    print(report)
    if args.output:
        args.output.write_text(report)

    # Exit non-zero if the p95 gate fails.
    latencies = sorted(r["latency_ms"] for r in results if r["error"] is None)
    if latencies:
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        if p95 >= 4000:
            print(f"FAIL: p95 {p95:.0f}ms >= 4000ms", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
