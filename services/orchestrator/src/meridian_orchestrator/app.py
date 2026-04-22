"""Module-level ASGI app entrypoint for uvicorn.

Construction of the Orchestrator from environment variables happens here.
The Dockerfile's CMD points at this module; uvicorn imports `app` and
serves it.

For tests, use `build_app()` directly with a pre-built Orchestrator; this
module is the production wiring.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import FastAPI
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ModelTier,
    PromptTemplate,
    TokenBudget,
)
from meridian_cost_accounting import CostAccountant, PerUserDailyTracker
from meridian_model_gateway import resilient_client
from meridian_prompt_registry import ActiveTemplateNotFoundError, PromptRegistry
from meridian_retrieval_client import (
    HttpRetrievalClient,
    MockRetrievalClient,
    RetrievalConfig,
    ThresholdingClient,
)
from meridian_retrieval_client.mock import FixtureEntry
from meridian_telemetry import OTelExporter, Tracer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meridian_orchestrator.api import AppConfig, build_app
from meridian_orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


class _RegistryTemplateProvider(TemplateProvider):
    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def get_active(self, name: str, environment: str) -> PromptTemplate:
        return self._registry.get_active(name, environment)


class _FileTemplateProvider(TemplateProvider):
    """Fallback when DATABASE_URL is not configured; reads prompts/ directly."""

    def get_active(self, name: str, environment: str) -> PromptTemplate:
        from datetime import UTC, datetime

        path = REPO_ROOT / "prompts" / name / "v1.yaml"
        raw = yaml.safe_load(path.read_text())
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
                environment=environment,
                status=ActivationStatus.DRAFT,
                canary_percentage=0,
                activated_at=datetime.now(tz=UTC),
                activated_by="staging@meridian.example",
            ),
        )


def _build_template_provider() -> TemplateProvider:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        return _FileTemplateProvider()
    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _RegistryTemplateProvider(PromptRegistry(session_factory))


def _build_retrieval_client() -> MockRetrievalClient | ThresholdingClient:
    base_url = os.environ.get("RAG_BASE_URL", "")
    if not base_url:
        return MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])])
    inner = HttpRetrievalClient(RetrievalConfig.from_env())
    return ThresholdingClient(inner=inner, min_relevance=0.5)


@lru_cache(maxsize=1)
def _orchestrator() -> Orchestrator:
    if os.environ.get("OTEL_ENABLED", "false").lower() in ("1", "true", "yes"):
        tracer = Tracer(
            service="meridian-orchestrator",
            exporter=OTelExporter(service_name="meridian-orchestrator"),
        )
    else:
        tracer = Tracer(service="meridian-orchestrator")
    return Orchestrator(
        templates=_build_template_provider(),
        retrieval=_build_retrieval_client(),
        model_client=resilient_client(),
        tracer=tracer,
        cost_accountant=CostAccountant(),
        user_spend_tracker=PerUserDailyTracker(),
        config=OrchestratorConfig(environment=os.environ.get("MERIDIAN_ENV", "staging")),
    )


def _readiness_check() -> bool:
    try:
        _orchestrator().templates.get_active(
            "classifier", os.environ.get("MERIDIAN_ENV", "staging")
        )
    except ActiveTemplateNotFoundError:
        return False
    except Exception:
        return False
    return True


app: FastAPI = build_app(
    _orchestrator(),
    config=AppConfig(environment=os.environ.get("MERIDIAN_ENV", "staging")),
    readiness_check=_readiness_check,
)
