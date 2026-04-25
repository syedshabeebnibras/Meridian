"""Production wiring — every dependency is built here.

``app.py`` is intentionally thin: it imports ``build_app_from_env()`` from
this module and exports the resulting ASGI app. Each external dependency
(template provider, session store, semantic cache, guardrails, feedback
store, audit sink, rate limiter, cost accounting) gets its own
``build_*()`` factory so:

  - Tests can replace one piece without rebuilding the world.
  - Operators can read this file top-to-bottom and see exactly what
    runs in staging/production vs. dev.
  - Capability inspection (``/debug/config``) reads from a single
    ``CapabilityReport`` so we never lie about what's enabled.

Environment variables consumed:

    MERIDIAN_ENV                          — staging | production | dev | test
    DATABASE_URL                          — Postgres URL (templates, sessions,
                                            semantic cache, audit, feedback)
    REDIS_URL                             — session conversation history
    RAG_BASE_URL                          — external retrieval service
    OPENAI_API_KEY                        — embeddings (semantic cache)
    OTEL_ENABLED                          — emit OTel spans
    LITELLM_BASE_URL                      — model gateway
    ORCH_INTERNAL_KEY                     — required in staging/prod
    LLAMA_GUARD_BASE_URL / _API_KEY       — optional input guardrail
    PATRONUS_API_KEY                      — optional output guardrail
    MERIDIAN_SEMANTIC_CACHE_ENABLED       — opt-in
    MERIDIAN_DAILY_BUDGET_USD             — cost circuit breaker
    MERIDIAN_RATELIMIT_ENABLED / _BURST / _PER_SECOND
    MERIDIAN_PII_GUARDRAILS_ENABLED       — default true; flip off only for evals
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
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
from meridian_cost_accounting import (
    CostAccountant,
    CostCircuitBreaker,
    DailyTracker,
    PerUserDailyTracker,
    RedisDailyTracker,
    WorkspaceCostBreaker,
)
from meridian_guardrails import (
    GuardrailPipeline,
    LlamaGuardConfig,
    LlamaGuardInputGuardrail,
    PatronusConfig,
    PatronusLynxOutputGuardrail,
    RegexPIIInputGuardrail,
    RegexPIIOutputGuardrail,
)
from meridian_ingestion import IngestionService, LocalPgvectorRetrievalClient
from meridian_model_gateway import resilient_client
from meridian_ops import RateLimiter, RedisTokenBucketRateLimiter, TokenBucketRateLimiter
from meridian_prompt_registry import ActiveTemplateNotFoundError, PromptRegistry
from meridian_retrieval_client import (
    HttpRetrievalClient,
    MockRetrievalClient,
    RetrievalConfig,
    ThresholdingClient,
)
from meridian_retrieval_client.mock import FixtureEntry
from meridian_semantic_cache import (
    InMemorySemanticCache,
    OpenAIEmbedding,
    PostgresSemanticCache,
    SemanticCache,
    StaticEmbedding,
)
from meridian_session_store import InMemorySessionStore, RedisSessionStore, SessionStore
from meridian_telemetry import OTelExporter, Tracer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from meridian_orchestrator.admin import AdminOverride
from meridian_orchestrator.api import AppConfig, build_app
from meridian_orchestrator.audit import (
    AuditSink,
    InMemoryAuditSink,
    NullAuditSink,
    PostgresAuditSink,
)
from meridian_orchestrator.caller import CallerContext, build_require_caller_context
from meridian_orchestrator.feedback import (
    FeedbackStore,
    InMemoryFeedbackStore,
    PostgresFeedbackStore,
)
from meridian_orchestrator.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    TemplateProvider,
)
from meridian_orchestrator.sessions import SessionService

logger = logging.getLogger("meridian.wiring")

REPO_ROOT = Path(__file__).resolve().parents[4]
_PROD_ENVS = frozenset({"staging", "production", "prod"})


def _bool_env(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")


def _is_prod() -> bool:
    return os.environ.get("MERIDIAN_ENV", "staging").lower() in _PROD_ENVS


# ---------------------------------------------------------------------------
# Capability report — every builder updates this so /debug/config and ops
# logs can show what's actually wired without leaking secrets.
# ---------------------------------------------------------------------------
@dataclass
class CapabilityReport:
    environment: str
    version: str = "0.1.0"
    template_provider: str = "unknown"
    session_store_backend: str = "unknown"
    semantic_cache_backend: str = "disabled"
    retrieval_backend: str = "unknown"
    feedback_store: str = "unknown"
    audit_sink: str = "unknown"
    input_guardrails: list[str] = field(default_factory=list)
    output_guardrails: list[str] = field(default_factory=list)
    rate_limiter_backend: str = "disabled"
    cost_breaker_backend: str = "disabled"
    model_gateway_url: str = "redacted"
    tenant_aware: bool = False
    otel_enabled: bool = False
    internal_auth: str = "unknown"

    def to_safe_dict(self) -> dict[str, object]:
        """Redacted view safe to expose at /debug/config."""
        return {
            "environment": self.environment,
            "version": self.version,
            "template_provider": self.template_provider,
            "session_store_backend": self.session_store_backend,
            "semantic_cache_backend": self.semantic_cache_backend,
            "retrieval_backend": self.retrieval_backend,
            "feedback_store": self.feedback_store,
            "audit_sink": self.audit_sink,
            "input_guardrails": list(self.input_guardrails),
            "output_guardrails": list(self.output_guardrails),
            "rate_limiter_backend": self.rate_limiter_backend,
            "cost_breaker_backend": self.cost_breaker_backend,
            "model_gateway_url": self.model_gateway_url,
            "tenant_aware": self.tenant_aware,
            "otel_enabled": self.otel_enabled,
            "internal_auth": self.internal_auth,
        }


# ---------------------------------------------------------------------------
# DB session factory — shared across multiple builders so they all bind to
# the same engine.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def build_session_factory() -> sessionmaker[Session] | None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        return None
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


# ---------------------------------------------------------------------------
# Template provider
# ---------------------------------------------------------------------------
class _RegistryTemplateProvider(TemplateProvider):
    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def get_active(self, name: str, environment: str) -> PromptTemplate:
        return self._registry.get_active(name, environment)


class _FileTemplateProvider(TemplateProvider):
    """Fallback when DATABASE_URL is not configured; reads prompts/ directly."""

    def get_active(self, name: str, environment: str) -> PromptTemplate:
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


def build_template_provider(report: CapabilityReport) -> TemplateProvider:
    factory = build_session_factory()
    if factory is None:
        report.template_provider = "file"
        return _FileTemplateProvider()
    report.template_provider = "postgres"
    return _RegistryTemplateProvider(PromptRegistry(factory))


# ---------------------------------------------------------------------------
# Session store (Redis-backed conversation history)
# ---------------------------------------------------------------------------
def build_session_store(report: CapabilityReport) -> SessionStore:
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        report.session_store_backend = "in_memory"
        return InMemorySessionStore()
    try:
        import redis
    except ImportError:
        report.session_store_backend = "in_memory (redis lib missing)"
        return InMemorySessionStore()
    client = redis.Redis.from_url(redis_url)
    report.session_store_backend = "redis"
    return RedisSessionStore(redis_client=client)


# ---------------------------------------------------------------------------
# Semantic cache — Postgres in staging/prod, in-memory only for dev/test
# ---------------------------------------------------------------------------
def build_semantic_cache(report: CapabilityReport) -> SemanticCache | None:
    if not _bool_env("MERIDIAN_SEMANTIC_CACHE_ENABLED", default=False):
        report.semantic_cache_backend = "disabled"
        return None

    embedding = OpenAIEmbedding() if os.environ.get("OPENAI_API_KEY") else StaticEmbedding()

    factory = build_session_factory()
    if factory is not None and _is_prod():
        ttl = float(os.environ.get("MERIDIAN_SEMANTIC_CACHE_TTL_S", "3600"))
        report.semantic_cache_backend = "postgres"
        return PostgresSemanticCache(
            embedding_model=embedding,
            session_factory=factory,
            ttl_seconds=ttl,
        )
    # Even in dev with a DB we keep an opt-in for the postgres backend.
    if (
        factory is not None
        and not _is_prod()
        and _bool_env("MERIDIAN_SEMANTIC_CACHE_POSTGRES", default=False)
    ):
        report.semantic_cache_backend = "postgres"
        return PostgresSemanticCache(embedding_model=embedding, session_factory=factory)

    report.semantic_cache_backend = "in_memory"
    return InMemorySemanticCache(embedding_model=embedding)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def build_retrieval_client(
    report: CapabilityReport,
) -> MockRetrievalClient | ThresholdingClient | LocalPgvectorRetrievalClient:
    """Pick the right RetrievalClient.

    Priority:
        1. RAG_BASE_URL set    → external HTTP client wrapped in a 0.5
                                  relevance threshold.
        2. DATABASE_URL set    → tenant-scoped pgvector retrieval over
                                  ``document_chunks``. Reads workspace_id from
                                  the WORKSPACE_ID contextvar set by api.py.
        3. otherwise           → empty mock (dev / unit tests).
    """
    base_url = os.environ.get("RAG_BASE_URL", "")
    if base_url:
        inner = HttpRetrievalClient(RetrievalConfig.from_env())
        report.retrieval_backend = "http"
        return ThresholdingClient(inner=inner, min_relevance=0.5)

    factory = build_session_factory()
    if factory is not None:
        embedding = OpenAIEmbedding() if os.environ.get("OPENAI_API_KEY") else StaticEmbedding()
        report.retrieval_backend = "local_pgvector"
        return LocalPgvectorRetrievalClient(session_factory=factory, embedding_model=embedding)

    report.retrieval_backend = "mock"
    return MockRetrievalClient(fixtures=[FixtureEntry(match="", chunks=[])])


def build_ingestion_service(report: CapabilityReport) -> IngestionService | None:
    """The ingestion service requires a DB. Without one, /v1/documents is
    not registered and the documents page renders the empty state."""
    factory = build_session_factory()
    if factory is None:
        return None
    # We deliberately do NOT mutate the capability report here — the report's
    # ``retrieval_backend`` already tells the operator whether the local
    # pgvector path is wired, and the embedding choice (OpenAI vs static) is
    # an internal detail covered by the same env vars as the semantic cache.
    embedding = OpenAIEmbedding() if os.environ.get("OPENAI_API_KEY") else StaticEmbedding()
    _ = report  # kept on the signature for future capability flags
    return IngestionService(session_factory=factory, embedding_model=embedding)


# ---------------------------------------------------------------------------
# Guardrails — regex PII always on; LlamaGuard / Patronus opt-in by env.
# ---------------------------------------------------------------------------
# Fail-safe behavior: when an external guardrail's HTTP endpoint is down or
# slow, the underlying client returns a PASS outcome with an "error" tag.
# We log but do not block — getting an answer is preferable to 5xx-ing the
# request stream. PII regex still runs locally so the obvious leaks are
# always caught.
def build_input_guardrails(report: CapabilityReport) -> GuardrailPipeline | None:
    enabled: list[object] = []
    names: list[str] = []
    if _bool_env("MERIDIAN_PII_GUARDRAILS_ENABLED", default=True):
        enabled.append(RegexPIIInputGuardrail())
        names.append("regex_pii")
    if os.environ.get("LLAMA_GUARD_BASE_URL"):
        enabled.append(LlamaGuardInputGuardrail(config=LlamaGuardConfig.from_env()))
        names.append("llama_guard")
    report.input_guardrails = names
    if not enabled:
        return None
    return GuardrailPipeline(guardrails=enabled)


def build_output_guardrails(report: CapabilityReport) -> GuardrailPipeline | None:
    enabled: list[object] = []
    names: list[str] = []
    if _bool_env("MERIDIAN_PII_GUARDRAILS_ENABLED", default=True):
        enabled.append(RegexPIIOutputGuardrail())
        names.append("regex_pii")
    if os.environ.get("PATRONUS_API_KEY"):
        enabled.append(PatronusLynxOutputGuardrail(config=PatronusConfig.from_env()))
        names.append("patronus_lynx")
    report.output_guardrails = names
    if not enabled:
        return None
    return GuardrailPipeline(guardrails=enabled)


# ---------------------------------------------------------------------------
# Feedback / audit
# ---------------------------------------------------------------------------
def build_feedback_store(report: CapabilityReport) -> FeedbackStore:
    factory = build_session_factory()
    if factory is None:
        report.feedback_store = "in_memory"
        if _is_prod():
            logger.warning(
                "feedback store is in-memory in MERIDIAN_ENV=%s — set DATABASE_URL "
                "for durable feedback.",
                os.environ.get("MERIDIAN_ENV"),
            )
        return InMemoryFeedbackStore()
    report.feedback_store = "postgres"
    return PostgresFeedbackStore(session_factory=factory)


def build_audit_sink(report: CapabilityReport) -> AuditSink:
    if not _bool_env("MERIDIAN_AUDIT_ENABLED", default=True):
        report.audit_sink = "disabled"
        return NullAuditSink()
    factory = build_session_factory()
    if factory is None:
        report.audit_sink = "in_memory"
        if _is_prod():
            logger.warning(
                "audit sink is in-memory in MERIDIAN_ENV=%s — events will be "
                "lost on restart. Set DATABASE_URL.",
                os.environ.get("MERIDIAN_ENV"),
            )
        return InMemoryAuditSink()
    report.audit_sink = "postgres"
    return PostgresAuditSink(session_factory=factory)


# ---------------------------------------------------------------------------
# Rate limiter / cost
# ---------------------------------------------------------------------------
def build_rate_limiter(report: CapabilityReport) -> RateLimiter | None:
    """Pick the strongest available limiter.

    Priority: Redis (when REDIS_URL is set) → in-process token bucket → off.
    The Redis impl uses an atomic Lua script so multiple uvicorn workers
    share one bucket per key; the in-process one only protects a single
    process and is wrong under ``--workers >1``.
    """
    if not _bool_env("MERIDIAN_RATELIMIT_ENABLED", default=True):
        report.rate_limiter_backend = "disabled"
        return None
    capacity = float(os.environ.get("MERIDIAN_RATELIMIT_BURST", "30"))
    refill = float(os.environ.get("MERIDIAN_RATELIMIT_PER_SECOND", "1"))
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            import redis

            client = redis.Redis.from_url(redis_url)
            report.rate_limiter_backend = "redis_token_bucket"
            return RedisTokenBucketRateLimiter(
                redis_client=client, capacity=capacity, refill_per_second=refill
            )
        except Exception as exc:
            logger.warning("redis rate limiter unavailable, falling back to in-process: %s", exc)
    report.rate_limiter_backend = "in_process_token_bucket"
    if _is_prod():
        logger.warning(
            "rate limiter is in-process in MERIDIAN_ENV=%s — limits are NOT shared "
            "across workers. Set REDIS_URL to enable distributed limiting.",
            os.environ.get("MERIDIAN_ENV"),
        )
    return TokenBucketRateLimiter(capacity=capacity, refill_per_second=refill)


def build_cost_breaker(report: CapabilityReport) -> CostCircuitBreaker:
    daily_budget = Decimal(os.environ.get("MERIDIAN_DAILY_BUDGET_USD", "100"))
    report.cost_breaker_backend = "in_process"
    return CostCircuitBreaker(daily_budget_usd=daily_budget)


# ---------------------------------------------------------------------------
# Distributed daily tracker + per-workspace breaker (Phase 4)
# ---------------------------------------------------------------------------
def build_daily_tracker() -> DailyTracker:
    """Per-(scope, day) spend ledger. Redis-backed when available."""
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            import redis

            return RedisDailyTracker(redis_client=redis.Redis.from_url(redis_url))
        except Exception as exc:
            logger.warning("redis daily tracker unavailable, falling back: %s", exc)
    return PerUserDailyTracker()


def build_workspace_breaker(tracker: DailyTracker) -> WorkspaceCostBreaker | None:
    raw = os.environ.get("MERIDIAN_WORKSPACE_DAILY_BUDGET_USD", "")
    if not raw:
        return None
    return WorkspaceCostBreaker(tracker=tracker, daily_budget_usd=Decimal(raw))


def build_admin_override() -> AdminOverride:
    return AdminOverride.from_env()


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------
def build_tracer(report: CapabilityReport) -> Tracer:
    if _bool_env("OTEL_ENABLED", default=False):
        report.otel_enabled = True
        return Tracer(
            service="meridian-orchestrator",
            exporter=OTelExporter(service_name="meridian-orchestrator"),
        )
    report.otel_enabled = False
    return Tracer(service="meridian-orchestrator")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def build_orchestrator(report: CapabilityReport) -> Orchestrator:
    return Orchestrator(
        templates=build_template_provider(report),
        retrieval=build_retrieval_client(report),
        model_client=resilient_client(),
        tracer=build_tracer(report),
        cost_accountant=CostAccountant(),
        user_spend_tracker=PerUserDailyTracker(),
        cost_breaker=build_cost_breaker(report),
        session_store=build_session_store(report),
        semantic_cache=build_semantic_cache(report),
        input_guardrails=build_input_guardrails(report),
        output_guardrails=build_output_guardrails(report),
        config=OrchestratorConfig(environment=os.environ.get("MERIDIAN_ENV", "staging")),
    )


# ---------------------------------------------------------------------------
# Readiness probe — every hard dependency must be reachable before /readyz
# returns 200. Load balancers should drain the pod when this fails.
# ---------------------------------------------------------------------------
def build_readiness_check(orchestrator: Orchestrator) -> Callable[[], bool]:
    env = os.environ.get("MERIDIAN_ENV", "staging")

    def check() -> bool:
        try:
            orchestrator.templates.get_active("classifier", env)
        except ActiveTemplateNotFoundError:
            return False
        except Exception:
            return False

        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            try:
                import redis

                redis.Redis.from_url(redis_url, socket_connect_timeout=1.0).ping()
            except Exception:
                return False

        litellm_base_url = os.environ.get("LITELLM_BASE_URL", "")
        if litellm_base_url:
            import httpx

            try:
                httpx.get(
                    f"{litellm_base_url.rstrip('/')}/health/liveliness",
                    timeout=2.0,
                ).raise_for_status()
            except Exception:
                return False

        return True

    return check


# ---------------------------------------------------------------------------
# Top-level: build the FastAPI app from environment.
# ---------------------------------------------------------------------------
def build_app_from_env() -> tuple[FastAPI, CapabilityReport]:
    """Construct the production ASGI app + capability report.

    Returned as a tuple so app.py can expose the report for
    /debug/config without re-running every builder.
    """
    env = os.environ.get("MERIDIAN_ENV", "staging")
    report = CapabilityReport(environment=env)

    orchestrator = build_orchestrator(report)
    feedback_store = build_feedback_store(report)
    audit_sink = build_audit_sink(report)
    rate_limiter = build_rate_limiter(report)
    admin_override = build_admin_override()
    ingestion_service = build_ingestion_service(report)

    factory = build_session_factory()
    session_service: SessionService | None = None
    require_caller: Callable[..., CallerContext] | None = None
    if factory is not None:
        session_service = SessionService(factory)
        # build_require_caller_context returns an async dep, which FastAPI awaits.
        # Pyright/mypy see ``Awaitable[CallerContext]`` as the return; the wider
        # ``Callable[..., CallerContext]`` shape in build_app() is what we
        # actually want at runtime.
        require_caller = build_require_caller_context(factory)  # type: ignore[assignment]
        report.tenant_aware = True
    else:
        report.tenant_aware = False
        if _is_prod():
            logger.warning(
                "DATABASE_URL not set — orchestrator booting in legacy "
                "(non-tenant-aware) mode. /v1/chat will accept user_id from "
                "the request body. NEVER ship to production this way."
            )

    # Capture internal auth state for the report. InternalAuthConfig.from_env()
    # is invoked again inside build_app(); consistent semantics, harmless.
    from meridian_orchestrator.auth import InternalAuthConfig

    auth_cfg = InternalAuthConfig.from_env()
    report.internal_auth = "dev_bypass" if auth_cfg.dev_mode else "x_internal_key"

    app = build_app(
        orchestrator,
        config=AppConfig(environment=env, version=report.version),
        feedback_store=feedback_store,
        rate_limiter=rate_limiter,
        admin_override=admin_override,
        session_service=session_service,
        require_caller=require_caller,
        audit_sink=audit_sink,
        capability_report=report,
        readiness_check=build_readiness_check(orchestrator),
        ingestion_service=ingestion_service,
    )
    logger.info("meridian orchestrator wired: %s", report.to_safe_dict())
    return app, report
