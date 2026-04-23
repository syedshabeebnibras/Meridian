"""Weekly production review — Section 11 + Section 18.

Every Monday, the team reviews the top 20 lowest-scoring traces from the
past week. This script builds the working document:

  1. Pull bottom-20 eval_results rows by faithfulness (past 7 days)
  2. Group by intent + prompt_version
  3. Emit a markdown action list sorted by repeat-count (patterns first)

Runs against Postgres eval_results. Use --from-jsonl for offline review
when you've exported a dump.

Usage:
  uv run python scripts/weekly_review.py --output /tmp/weekly.md
  uv run python scripts/weekly_review.py --from-jsonl dump.jsonl --output /tmp/weekly.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass
class Trace:
    eval_id: str
    request_id: str
    score: float
    intent: str
    prompt_version: str
    model_used: str
    timestamp: datetime


def _load_from_postgres(database_url: str, days: int) -> list[Trace]:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)

    with session_factory() as session:
        rows = session.execute(
            text(
                """
                SELECT eval_id, request_id, (scores->>'faithfulness')::float AS score,
                       COALESCE(scores->>'intent', 'unknown') AS intent,
                       prompt_version, model_used, timestamp
                FROM eval_results
                WHERE timestamp >= :cutoff
                  AND eval_type = 'online_sample'
                  AND scores ? 'faithfulness'
                ORDER BY score ASC NULLS LAST
                LIMIT 20
                """
            ),
            {"cutoff": cutoff},
        ).all()

    return [
        Trace(
            eval_id=row[0],
            request_id=row[1],
            score=float(row[2]) if row[2] is not None else 0.0,
            intent=row[3],
            prompt_version=row[4],
            model_used=row[5],
            timestamp=row[6],
        )
        for row in rows
    ]


def _load_from_jsonl(path: Path) -> list[Trace]:
    traces: list[Trace] = []
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            scores = row.get("scores", {})
            traces.append(
                Trace(
                    eval_id=row["eval_id"],
                    request_id=row["request_id"],
                    score=float(scores.get("faithfulness", 0.0)),
                    intent=row.get("intent", "unknown"),
                    prompt_version=row["prompt_version"],
                    model_used=row["model_used"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                )
            )
    traces.sort(key=lambda t: t.score)
    return traces[:20]


def _render(traces: list[Trace]) -> str:
    if not traces:
        return "# Weekly review\n\nNo low-scoring traces in the past 7 days — celebrate, then double-check sampling.\n"

    intent_counts = Counter(t.intent for t in traces)
    version_counts = Counter(t.prompt_version for t in traces)
    by_intent: dict[str, list[Trace]] = defaultdict(list)
    for t in traces:
        by_intent[t.intent].append(t)

    lines: list[str] = [
        "# Weekly review",
        f"_Generated: {datetime.now(tz=UTC).isoformat()}_",
        "",
        "## Summary",
        f"- Traces reviewed: {len(traces)}",
        f"- Mean faithfulness: {sum(t.score for t in traces) / len(traces):.3f}",
        "- Top intents in the set: "
        + ", ".join(f"{i} ({c})" for i, c in intent_counts.most_common(3)),
        "- Top prompt versions: "
        + ", ".join(f"{v} ({c})" for v, c in version_counts.most_common(3)),
        "",
        "## Pattern hypotheses",
    ]

    # Surface repeat-offenders: if one (intent, prompt_version) pair accounts
    # for >= 4 of the 20 traces, that's a strong signal.
    pair_counts: Counter[tuple[str, str]] = Counter((t.intent, t.prompt_version) for t in traces)
    for (intent, version), count in pair_counts.most_common(3):
        if count >= 4:
            lines.append(
                f"- `{intent}` + `{version}` appeared {count} times — investigate this pair first"
            )
    if not any(c >= 4 for c in pair_counts.values()):
        lines.append("- No single intent+version pair dominates; issues are dispersed.")

    lines.extend(["", "## Trace drill-down"])
    for i, t in enumerate(sorted(traces, key=lambda x: x.score), start=1):
        lines.append(
            f"{i}. score={t.score:.2f}  intent={t.intent}  prompt={t.prompt_version}  "
            f"model={t.model_used}  request_id=`{t.request_id}`"
        )

    lines.extend(
        [
            "",
            "## Suggested actions",
            "1. Open the 3 lowest-scoring traces in Langfuse and read them end-to-end.",
            "2. If a pattern hypothesis holds, file a prompt-tuning ticket against the named version.",
            "3. Add any reproducible failure to `datasets/grounded_qa_v1.yaml` via `scripts/promote_to_golden.py`.",
            "4. If a guardrail FP rate is the cause, open an entry in `tasks/lessons.md`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://meridian:meridian@localhost:5432/meridian",
        ),
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--from-jsonl", type=Path, help="Load from an eval_results dump (offline)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        if args.from_jsonl is not None:
            traces = _load_from_jsonl(args.from_jsonl)
        else:
            traces = _load_from_postgres(args.database_url, args.days)
    except Exception as exc:
        print(f"failed to load traces: {exc}", file=sys.stderr)
        return 1

    report = _render(traces)
    print(report)
    if args.output:
        args.output.write_text(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
