"""60-second staging smoke — Section 12 Phase 7 post-deploy sanity check.

Hits healthz / readyz and fires one query per intent category. Exits
non-zero on any hard failure. Call from the deploy script.

Usage:
  STAGING_URL=https://meridian-orch.fly.dev uv run python scripts/staging_smoke.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any

import httpx


def _env_url() -> str:
    url = os.environ.get("STAGING_URL", "").rstrip("/")
    if not url:
        print("STAGING_URL env var is required", file=sys.stderr)
        sys.exit(1)
    return url


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}{(': ' + detail) if detail else ''}")
    return ok


def _request(url: str, query: str) -> dict[str, Any] | None:
    payload = {
        "request_id": f"req_smoke{uuid.uuid4().hex[:12]}",
        "user_id": "smoke",
        "session_id": f"smoke_{uuid.uuid4().hex[:8]}",
        "query": query,
        "conversation_history": [],
        "metadata": {"source": "smoke"},
    }
    try:
        response = httpx.post(f"{url}/v1/chat", json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def main() -> int:
    url = _env_url()
    print(f"Smoke-testing {url}")

    all_ok = True

    # 1. Healthz
    try:
        r = httpx.get(f"{url}/healthz", timeout=5)
        all_ok &= _check("healthz", r.status_code == 200 and r.text.strip() == "ok")
    except httpx.HTTPError as exc:
        all_ok = _check("healthz", False, str(exc)) and all_ok

    # 2. Readyz
    try:
        r = httpx.get(f"{url}/readyz", timeout=5)
        all_ok &= _check("readyz", r.status_code == 200)
    except httpx.HTTPError as exc:
        all_ok = _check("readyz", False, str(exc)) and all_ok

    # 3. Metrics endpoint
    try:
        r = httpx.get(f"{url}/metrics", timeout=5)
        all_ok &= _check("metrics", r.status_code == 200 and "meridian_requests_total" in r.text)
    except httpx.HTTPError as exc:
        all_ok = _check("metrics", False, str(exc)) and all_ok

    # 4. One query per intent category — verifies the full stack is wired
    smoke_queries = {
        "grounded_qa": "What is the escalation procedure for a P1 database outage?",
        "out_of_scope": "What's the weather in Tokyo?",
        "clarification": "What about that?",
    }
    for intent, query in smoke_queries.items():
        started = time.perf_counter()
        reply = _request(url, query)
        latency_ms = (time.perf_counter() - started) * 1000
        if reply is None:
            all_ok = _check(f"query/{intent}", False, "request failed") and all_ok
            continue
        status = reply.get("status")
        all_ok &= _check(
            f"query/{intent}",
            status in ("ok", "refused", "blocked"),
            f"status={status}, {latency_ms:.0f}ms",
        )
        # Latency must be under the Section-12 gate.
        all_ok &= _check(
            f"query/{intent} latency < 4s",
            latency_ms < 4000,
            f"{latency_ms:.0f}ms",
        )

    print()
    print("SMOKE: PASS" if all_ok else "SMOKE: FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
