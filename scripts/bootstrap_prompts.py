"""Load every prompts/**/v*.yaml file into the registry.

Idempotent: if the current content equals the latest version already stored,
the file is skipped. Otherwise a new immutable version is created (and
optionally activated in the target environment).

Usage:
    uv run python scripts/bootstrap_prompts.py                       # load only
    uv run python scripts/bootstrap_prompts.py --activate --env dev  # load + activate
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelTier,
    PromptTemplate,
    TokenBudget,
)
from meridian_prompt_registry import (
    ActiveTemplateNotFoundError,
    PromptRegistry,
    PromptVersionNotFoundError,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return raw


def _to_template(raw: dict[str, Any]) -> PromptTemplate:
    """Turn a YAML dict into a draft PromptTemplate.

    Version and activation are filled in by the registry, so we pass
    placeholder values that the registry ignores.
    """
    return PromptTemplate(
        name=raw["name"],
        version=1,  # ignored — registry auto-increments
        model_tier=ModelTier(raw["model_tier"]),
        min_model=raw["min_model"],
        template=raw["template"],
        parameters=raw["parameters"],
        schema_ref=raw["schema_ref"],
        few_shot_dataset=raw.get("few_shot_dataset"),
        token_budget=TokenBudget.model_validate(raw["token_budget"]),
        cache_control=CacheControl.model_validate(raw["cache_control"]),
        activation=ActivationInfo(
            environment="bootstrap",
            status=ActivationStatus.DRAFT,
            canary_percentage=0,
            activated_at=datetime.now(tz=UTC),
            activated_by="bootstrap@meridian.example",
        ),
    )


def _is_duplicate(existing: PromptTemplate, candidate: PromptTemplate) -> bool:
    """Skip condition — the *content* of the existing latest version matches."""
    return (
        existing.template == candidate.template
        and existing.model_tier == candidate.model_tier
        and existing.min_model == candidate.min_model
        and existing.parameters == candidate.parameters
        and existing.schema_ref == candidate.schema_ref
        and existing.few_shot_dataset == candidate.few_shot_dataset
        and existing.token_budget == candidate.token_budget
        and existing.cache_control == candidate.cache_control
    )


def _latest_version(registry: PromptRegistry, name: str) -> PromptTemplate | None:
    versions = registry.list_versions(name)
    return versions[-1] if versions else None


def _discover() -> list[Path]:
    """Find every v*.yaml file under prompts/."""
    return sorted(PROMPTS_DIR.rglob("v*.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://meridian:meridian@localhost:5432/meridian",
        ),
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="After create_version, activate the new version in --env.",
    )
    parser.add_argument(
        "--env",
        default="dev",
        help="Environment to activate in when --activate is passed.",
    )
    parser.add_argument(
        "--actor",
        default="bootstrap@meridian.example",
        help="Audit-log actor for create/activate entries.",
    )
    args = parser.parse_args()

    engine = create_engine(args.database_url, future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    registry = PromptRegistry(session_factory)

    files = _discover()
    if not files:
        print(f"no prompt YAML files found under {PROMPTS_DIR}")
        return 0

    for path in files:
        raw = _load_yaml(path)
        candidate = _to_template(raw)
        latest = _latest_version(registry, candidate.name)

        if latest and _is_duplicate(latest, candidate):
            print(f"  skip   {candidate.name} — content matches v{latest.version}")
            continue

        version = registry.create_version(candidate, created_by=args.actor)
        print(f"  create {candidate.name} v{version} from {path.relative_to(REPO_ROOT)}")

        if args.activate:
            try:
                active = registry.get_active(candidate.name, args.env)
                prior_version = active.version
            except ActiveTemplateNotFoundError:
                prior_version = None
            registry.activate(
                candidate.name,
                version=version,
                environment=args.env,
                actor=args.actor,
                reason=f"bootstrap from {path.name}",
            )
            if prior_version is None:
                print(f"         activated in {args.env} (first activation)")
            else:
                print(f"         activated in {args.env} (was v{prior_version})")

    # Final summary — quickly confirm each template has something active.
    if args.activate:
        print("")
        print(f"Active templates in env={args.env}:")
        for path in files:
            name = _load_yaml(path)["name"]
            try:
                active = registry.get_active(name, args.env)
                print(f"  {name:20s} v{active.version}")
            except (ActiveTemplateNotFoundError, PromptVersionNotFoundError):
                print(f"  {name:20s} <not active>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
