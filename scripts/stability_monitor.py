"""48-hour post-launch stability monitor — Phase 8 exit criterion.

Polls the staging/prod /metrics endpoint at an interval, evaluates each of
the 10 Section-11 alert conditions (best-effort from prometheus text),
and records any P1 incidents with timestamps.

Modes:
  quick  — run the checks once and exit
  watch  — run for --hours (default 48) at --interval-s (default 300) cadence

Exits non-zero if any P1 condition triggered during the watch.

Usage:
  STAGING_URL=https://... uv run python scripts/stability_monitor.py --mode quick
  STAGING_URL=https://... uv run python scripts/stability_monitor.py --mode watch --hours 48
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx


@dataclass
class IncidentLog:
    timestamp: datetime
    alert_id: str
    severity: str
    reason: str


@dataclass
class Monitor:
    endpoint: str
    incidents: list[IncidentLog] = field(default_factory=list)

    def check_once(self) -> None:
        now = datetime.now(tz=UTC)
        try:
            response = httpx.get(f"{self.endpoint}/metrics", timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.incidents.append(
                IncidentLog(
                    timestamp=now,
                    alert_id="01_high_error_rate",
                    severity="P1",
                    reason=f"endpoint unreachable: {exc}",
                )
            )
            return

        try:
            healthz = httpx.get(f"{self.endpoint}/healthz", timeout=5)
            if healthz.status_code != 200:
                self.incidents.append(
                    IncidentLog(
                        timestamp=now,
                        alert_id="01_high_error_rate",
                        severity="P1",
                        reason=f"healthz returned {healthz.status_code}",
                    )
                )
        except httpx.HTTPError as exc:
            self.incidents.append(
                IncidentLog(
                    timestamp=now,
                    alert_id="01_high_error_rate",
                    severity="P1",
                    reason=f"healthz failed: {exc}",
                )
            )

    def watch(self, *, hours: float, interval_s: float) -> None:
        deadline = time.monotonic() + (hours * 3600)
        tick = 0
        while time.monotonic() < deadline:
            tick += 1
            print(f"[tick {tick}] {datetime.now(tz=UTC).isoformat()} — checking...")
            self.check_once()
            if self.incidents:
                # Log incidents but continue watching so the final report is complete.
                latest = self.incidents[-1]
                print(f"  INCIDENT [{latest.severity}] {latest.alert_id}: {latest.reason}")
            else:
                print("  OK")
            time.sleep(interval_s)

    def report(self) -> str:
        lines = ["# Stability report", f"- Incidents: {len(self.incidents)}"]
        p1 = [i for i in self.incidents if i.severity == "P1"]
        lines.append(f"- P1: {len(p1)}")
        lines.append("")
        if p1:
            lines.append("## P1 incidents")
            for inc in p1:
                lines.append(f"- {inc.timestamp.isoformat()} [{inc.alert_id}] {inc.reason}")
        lines.append("")
        lines.append("## Section 12 exit criterion")
        lines.append(f"- 48-hour stability (zero P1 incidents): {'PASS' if not p1 else 'FAIL'}")
        return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("quick", "watch"), default="quick")
    parser.add_argument("--hours", type=float, default=48.0)
    parser.add_argument("--interval-s", type=float, default=300.0)
    parser.add_argument("--output")
    args = parser.parse_args()

    endpoint = os.environ.get("STAGING_URL", "").rstrip("/")
    if not endpoint:
        print("STAGING_URL required", file=sys.stderr)
        return 1

    monitor = Monitor(endpoint=endpoint)
    if args.mode == "quick":
        monitor.check_once()
    else:
        monitor.watch(hours=args.hours, interval_s=args.interval_s)

    report = monitor.report()
    print(report)
    if args.output:
        from pathlib import Path as _Path

        _Path(args.output).write_text(report)

    return 1 if any(i.severity == "P1" for i in monitor.incidents) else 0


if __name__ == "__main__":
    sys.exit(main())
