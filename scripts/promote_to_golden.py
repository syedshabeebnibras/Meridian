"""Promote production failure cases into the golden dataset.

Section 10 §Golden dataset update cadence: add 10 new examples from
production logs every 2 weeks, prioritizing failure cases + edge cases.

Reads eval_results, picks up to --limit traces below --max-score, and
writes a YAML file of candidates for SME review + manual merge into the
canonical dataset.

Usage:
  uv run python scripts/promote_to_golden.py --output datasets/golden_candidates.yaml
  uv run python scripts/promote_to_golden.py --max-score 0.7 --limit 20 --days 14
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml


def _load_candidates(
    database_url: str, *, max_score: float, days: int, limit: int
) -> list[dict[str, object]]:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)

    with session_factory() as session:
        rows = session.execute(
            text(
                """
                SELECT request_id, scores, prompt_version, model_used, timestamp
                FROM eval_results
                WHERE timestamp >= :cutoff
                  AND (scores->>'faithfulness')::float < :max_score
                  AND human_label IS NOT NULL
                ORDER BY (scores->>'faithfulness')::float ASC
                LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "max_score": max_score, "limit": limit},
        ).all()

    candidates: list[dict[str, object]] = []
    for row in rows:
        candidates.append(
            {
                "source_request_id": row[0],
                "scores": row[1],
                "prompt_version": row[2],
                "model_used": row[3],
                "timestamp": row[4].isoformat() if row[4] else None,
                "reviewer_action": "pending",  # SME fills in
                "golden_answer": "<SME: paste the expected answer>",
                "expected_citations": [],
                "notes": "",
            }
        )
    return candidates


def _render(candidates: list[dict[str, object]]) -> str:
    header = {
        "dataset_name": "golden_candidates",
        "task_type": "grounded_qa",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "scripts/promote_to_golden.py",
        "review_instructions": (
            "Each candidate needs an SME to: "
            "(1) paste the expected answer; "
            "(2) mark reviewer_action='accept' or 'reject'; "
            "(3) add citations the answer should cite."
        ),
        "candidates": candidates,
    }
    return yaml.safe_dump(header, sort_keys=False, default_flow_style=False, width=100)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://meridian:meridian@localhost:5432/meridian",
        ),
    )
    parser.add_argument("--max-score", type=float, default=0.75)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("datasets/golden_candidates.yaml"))
    args = parser.parse_args()

    try:
        candidates = _load_candidates(
            args.database_url, max_score=args.max_score, days=args.days, limit=args.limit
        )
    except Exception as exc:
        print(f"failed to load candidates: {exc}", file=sys.stderr)
        return 1

    report = _render(candidates)
    args.output.write_text(report)
    print(f"wrote {len(candidates)} candidates to {args.output}")
    if not candidates:
        print(
            "(no production failures matched — golden set is stable; pull from a longer window if needed)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
