"""Go/no-go promotion check — Phase 8.

Runs every launch-gate check that matters for the next rollout step and
reports a single PASS/FAIL. Callable before any `scripts/rollout.py set`
bump.

Sequence:
  1. Launch-gate metrics (scripts/check_launch_gates.py --client stub)
  2. Staging smoke (scripts/staging_smoke.py if STAGING_URL is set)
  3. Red-team suite (scripts/red_team.py if STAGING_URL is set)
  4. 48-hour stability (scripts/stability_monitor.py --mode quick)

Exits 0 if every check passes, non-zero if any fails.

Usage:
  STAGING_URL=https://meridian-orch.fly.dev uv run python scripts/go_no_go.py
  uv run python scripts/go_no_go.py --skip-red-team     # e.g. for dogfooding bump
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(label: str, cmd: list[str]) -> bool:
    print(f"\n=== {label} ===")
    print("+ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    ok = result.returncode == 0
    print(f"{label}: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-red-team", action="store_true")
    parser.add_argument("--skip-stability", action="store_true")
    args = parser.parse_args()

    staging_url = os.environ.get("STAGING_URL", "").rstrip("/")
    results: list[tuple[str, bool]] = []

    results.append(
        (
            "launch-gate metrics",
            _run(
                "Launch gate metrics",
                ["uv", "run", "python", "scripts/check_launch_gates.py", "--client", "stub"],
            ),
        )
    )

    if staging_url:
        results.append(
            (
                "staging smoke",
                _run(
                    "Staging smoke",
                    ["uv", "run", "python", "scripts/staging_smoke.py"],
                ),
            )
        )
        if not args.skip_red_team:
            results.append(
                (
                    "red team",
                    _run(
                        "Red-team suite",
                        [
                            "uv",
                            "run",
                            "python",
                            "scripts/red_team.py",
                            "--endpoint",
                            f"{staging_url}/v1/chat",
                        ],
                    ),
                )
            )
    else:
        print("\n(STAGING_URL not set — skipping smoke + red-team)")

    if not args.skip_stability and staging_url:
        results.append(
            (
                "48h stability (quick)",
                _run(
                    "48-hour stability (quick check)",
                    ["uv", "run", "python", "scripts/stability_monitor.py", "--mode", "quick"],
                ),
            )
        )

    print("\n=== Summary ===")
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    overall = all(ok for _, ok in results)
    print(f"\nGo/no-go: {'GO' if overall else 'NO-GO'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
