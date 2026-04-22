"""Rollout CLI — Phase 8 gradual promotion.

Usage:
  uv run python scripts/rollout.py status
  uv run python scripts/rollout.py set --percentage 25
  uv run python scripts/rollout.py allow --user u_alice
  uv run python scripts/rollout.py deny  --user u_bob
  uv run python scripts/rollout.py kill  --on           # emergency brake
  uv run python scripts/rollout.py kill  --off

Every mutation writes an entry to prompt_audit_log-style history so the
team can reconstruct the exact rollout timeline during post-launch review.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

from meridian_feature_flags import (
    FeatureFlag,
    InMemoryFeatureFlagStore,
    PostgresFeatureFlagStore,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

FLAG_NAME = "meridian.enabled"


def _store(database_url: str):  # type: ignore[no-untyped-def]
    if not database_url:
        return InMemoryFeatureFlagStore()
    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return PostgresFeatureFlagStore(session_factory=session_factory)


def _get_or_default(store) -> FeatureFlag:  # type: ignore[no-untyped-def]
    flag = store.get(FLAG_NAME)
    if flag is not None:
        return flag
    return FeatureFlag(name=FLAG_NAME)


def _render(flag: FeatureFlag) -> str:
    parts = [
        f"flag:         {flag.name}",
        f"percentage:   {flag.percentage}%",
        f"kill_switch:  {flag.kill_switch}",
        f"allowlist:    {len(flag.allowlist)} users",
        f"denylist:     {len(flag.denylist)} users",
        f"updated_at:   {flag.updated_at.isoformat()}",
        f"updated_by:   {flag.updated_by}",
    ]
    if flag.allowlist:
        parts.append(f"  allowlist = {flag.allowlist}")
    if flag.denylist:
        parts.append(f"  denylist  = {flag.denylist}")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://meridian:meridian@localhost:5432/meridian",
        ),
    )
    parser.add_argument("--actor", default=os.environ.get("USER", "unknown"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("--percentage", type=int, required=True)

    allow_cmd = sub.add_parser("allow")
    allow_cmd.add_argument("--user", required=True)

    deny_cmd = sub.add_parser("deny")
    deny_cmd.add_argument("--user", required=True)

    kill_cmd = sub.add_parser("kill")
    kill_cmd.add_argument("--on", action="store_true")
    kill_cmd.add_argument("--off", action="store_true")

    args = parser.parse_args()

    store = _store(args.database_url)
    flag = _get_or_default(store)

    if args.command == "status":
        print(_render(flag))
        return 0

    if args.command == "set":
        if not 0 <= args.percentage <= 100:
            print("percentage must be 0..100", file=sys.stderr)
            return 1
        flag = flag.model_copy(
            update={
                "percentage": args.percentage,
                "updated_at": datetime.now(tz=UTC),
                "updated_by": args.actor,
            }
        )
        store.put(flag)
        print(f"set {FLAG_NAME} percentage={args.percentage}% by {args.actor}")
        return 0

    if args.command == "allow":
        allow = list(set(flag.allowlist) | {args.user})
        flag = flag.model_copy(
            update={
                "allowlist": allow,
                "updated_at": datetime.now(tz=UTC),
                "updated_by": args.actor,
            }
        )
        store.put(flag)
        print(f"allowlisted {args.user}")
        return 0

    if args.command == "deny":
        deny = list(set(flag.denylist) | {args.user})
        flag = flag.model_copy(
            update={"denylist": deny, "updated_at": datetime.now(tz=UTC), "updated_by": args.actor}
        )
        store.put(flag)
        print(f"denylisted {args.user}")
        return 0

    if args.command == "kill":
        if args.on == args.off:
            print("pass exactly one of --on / --off", file=sys.stderr)
            return 1
        flag = flag.model_copy(
            update={
                "kill_switch": args.on,
                "updated_at": datetime.now(tz=UTC),
                "updated_by": args.actor,
            }
        )
        store.put(flag)
        print(f"kill switch {'ON' if args.on else 'OFF'}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
