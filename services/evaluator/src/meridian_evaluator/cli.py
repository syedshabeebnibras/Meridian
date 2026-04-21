"""Regression CLI — run a dataset end-to-end and print a report.

Examples:
    # Offline (uses stub_response from the YAML) — safe in CI without API keys.
    uv run python -m meridian_evaluator.cli \
        --dataset datasets/classifier_v1.yaml \
        --client stub --registry file

    # Live — hits LiteLLM (requires `make up` and real API keys).
    uv run python -m meridian_evaluator.cli \
        --dataset datasets/classifier_v1.yaml \
        --client live --registry postgres
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC
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
from meridian_model_gateway import LiteLLMClient, LiteLLMConfig
from meridian_prompt_registry import PromptRegistry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meridian_evaluator.datasets import (
    ClassifierExample,
    GoldenQAExample,
    load_dataset,
)
from meridian_evaluator.regressor import TIER_ALIAS, Regressor, make_default_scorer
from meridian_evaluator.reports import render_markdown_report
from meridian_evaluator.stub_client import StubModelClient

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_template_from_file(name: str) -> PromptTemplate:
    """Read prompts/<name>/v1.yaml directly — no DB round-trip."""
    from datetime import datetime

    path = REPO_ROOT / "prompts" / name / "v1.yaml"
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    return PromptTemplate(
        name=raw["name"],
        version=1,
        model_tier=ModelTier(raw["model_tier"]),
        min_model=raw["min_model"],
        template=raw["template"],
        parameters=raw["parameters"],
        schema_ref=raw["schema_ref"],
        few_shot_dataset=raw.get("few_shot_dataset"),
        token_budget=TokenBudget.model_validate(raw["token_budget"]),
        cache_control=CacheControl.model_validate(raw["cache_control"]),
        activation=ActivationInfo(
            environment="file",
            status=ActivationStatus.DRAFT,
            canary_percentage=0,
            activated_at=datetime.now(tz=UTC),
            activated_by="regressor@meridian.example",
        ),
    )


def _build_stub_client(dataset: Any, template: PromptTemplate) -> StubModelClient:
    """Register a canned response per example in the dataset."""
    client = StubModelClient()
    model_alias = TIER_ALIAS[template.model_tier]
    for ex in dataset.examples:
        if ex.stub_response is None:
            raise ValueError(
                f"example {ex.input!r} has no stub_response — can't run in offline mode"
            )
        if isinstance(ex, (ClassifierExample, GoldenQAExample)):
            client.register(
                model=model_alias,
                user_content_fragment=ex.input[:40],
                content=ex.stub_response.content,
                latency_ms=ex.stub_response.latency_ms,
            )
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--client", choices=("stub", "live"), default="stub")
    parser.add_argument(
        "--registry",
        choices=("file", "postgres"),
        default="file",
        help="Where to fetch the prompt template.",
    )
    parser.add_argument(
        "--env",
        default="dev",
        help="Environment name when --registry=postgres.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://meridian:meridian@localhost:5432/meridian",
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to write the full result as JSON.",
    )
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)

    # Fetch the template.
    if args.registry == "postgres":
        engine = create_engine(args.database_url, future=True)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        registry = PromptRegistry(session_factory)
        template = registry.get_active(dataset.prompt_name, args.env)
    else:
        template = _load_template_from_file(dataset.prompt_name)

    # Build the client.
    client = (
        _build_stub_client(dataset, template)
        if args.client == "stub"
        else LiteLLMClient(LiteLLMConfig.from_env())
    )

    # Run.
    scorer = make_default_scorer(dataset.task_type)
    regressor = Regressor(template=template, client=client, scorer=scorer)
    result = regressor.run(dataset, dataset_path=args.dataset)

    # Report.
    print(render_markdown_report(result))
    if args.json_out:
        args.json_out.write_text(json.dumps(result.model_dump(), indent=2))

    # Exit non-zero if pass rate is below the dataset-specific threshold.
    threshold = 0.80 if dataset.task_type == "classifier" else 0.75
    if result.pass_rate < threshold:
        print(
            f"FAIL: pass_rate {result.pass_rate:.2%} below threshold {threshold:.2%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
