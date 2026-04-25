"""Tests for ``meridian_orchestrator.wiring`` builders.

These tests don't hit a real DB — they just assert that each builder
populates the ``CapabilityReport`` correctly under different env-var
combinations. Postgres-backed builders are exercised against an
in-memory SQLite session in test_feedback_store / test_audit_sink.
"""

from __future__ import annotations

import pytest
from meridian_orchestrator.audit import InMemoryAuditSink, NullAuditSink
from meridian_orchestrator.feedback import InMemoryFeedbackStore
from meridian_orchestrator.wiring import (
    CapabilityReport,
    build_audit_sink,
    build_feedback_store,
    build_input_guardrails,
    build_output_guardrails,
    build_rate_limiter,
    build_semantic_cache,
    build_session_factory,
)


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe DATABASE_URL + clear lru_cache so each test sees a fresh build."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    build_session_factory.cache_clear()


def test_feedback_store_falls_back_to_memory_without_database() -> None:
    report = CapabilityReport(environment="test")
    store = build_feedback_store(report)
    assert isinstance(store, InMemoryFeedbackStore)
    assert report.feedback_store == "in_memory"


def test_audit_sink_falls_back_to_memory_without_database() -> None:
    report = CapabilityReport(environment="test")
    sink = build_audit_sink(report)
    assert isinstance(sink, InMemoryAuditSink)
    assert report.audit_sink == "in_memory"


def test_audit_sink_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_AUDIT_ENABLED", "false")
    report = CapabilityReport(environment="test")
    sink = build_audit_sink(report)
    assert isinstance(sink, NullAuditSink)
    assert report.audit_sink == "disabled"


def test_input_guardrails_default_to_regex_pii() -> None:
    report = CapabilityReport(environment="test")
    pipeline = build_input_guardrails(report)
    assert pipeline is not None
    assert report.input_guardrails == ["regex_pii"]


def test_input_guardrails_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_PII_GUARDRAILS_ENABLED", "false")
    report = CapabilityReport(environment="test")
    pipeline = build_input_guardrails(report)
    assert pipeline is None
    assert report.input_guardrails == []


def test_input_guardrails_pick_up_llama_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_GUARD_BASE_URL", "http://localhost:7100")
    report = CapabilityReport(environment="test")
    pipeline = build_input_guardrails(report)
    assert pipeline is not None
    assert report.input_guardrails == ["regex_pii", "llama_guard"]


def test_output_guardrails_pick_up_patronus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATRONUS_API_KEY", "test-key")
    report = CapabilityReport(environment="test")
    pipeline = build_output_guardrails(report)
    assert pipeline is not None
    assert report.output_guardrails == ["regex_pii", "patronus_lynx"]


def test_semantic_cache_disabled_by_default() -> None:
    report = CapabilityReport(environment="test")
    cache = build_semantic_cache(report)
    assert cache is None
    assert report.semantic_cache_backend == "disabled"


def test_semantic_cache_enabled_falls_back_to_memory_in_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_SEMANTIC_CACHE_ENABLED", "true")
    report = CapabilityReport(environment="test")
    cache = build_semantic_cache(report)
    assert cache is not None
    assert report.semantic_cache_backend == "in_memory"


def test_rate_limiter_enabled_by_default() -> None:
    report = CapabilityReport(environment="test")
    limiter = build_rate_limiter(report)
    assert limiter is not None
    assert report.rate_limiter_backend == "in_process_token_bucket"


def test_rate_limiter_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_RATELIMIT_ENABLED", "false")
    report = CapabilityReport(environment="test")
    limiter = build_rate_limiter(report)
    assert limiter is None
    assert report.rate_limiter_backend == "disabled"


def test_capability_report_safe_dict_excludes_no_secrets() -> None:
    """The redacted view must only contain backend-name strings, never secrets."""
    report = CapabilityReport(
        environment="production",
        input_guardrails=["regex_pii", "llama_guard"],
        output_guardrails=["regex_pii", "patronus_lynx"],
    )
    safe = report.to_safe_dict()
    blob = repr(safe)
    # No secret-shaped substrings (api keys, urls with credentials).
    assert "sk-" not in blob
    assert "://" not in blob  # no raw URLs leaked
    assert "password" not in blob.lower()
    assert safe["model_gateway_url"] == "redacted"


def test_capability_report_lists_are_independent() -> None:
    """to_safe_dict() returns copies — mutation must not bleed back."""
    report = CapabilityReport(environment="test", input_guardrails=["regex_pii"])
    safe = report.to_safe_dict()
    safe["input_guardrails"].append("nope")  # type: ignore[union-attr]
    assert report.input_guardrails == ["regex_pii"]


# ---------------------------------------------------------------------------
# Tool executor — opt-in by env, off by default
# ---------------------------------------------------------------------------
def test_tool_executor_disabled_when_env_unset() -> None:
    from meridian_orchestrator.wiring import build_tool_executor

    report = CapabilityReport(environment="test")
    assert build_tool_executor(report) is None
    assert report.tools == []


def test_tool_executor_registers_jira_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from meridian_orchestrator.wiring import build_tool_executor

    monkeypatch.setenv("JIRA_BASE_URL", "https://meridian.atlassian.net")
    monkeypatch.setenv("JIRA_API_TOKEN", "stub")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "ENG")
    monkeypatch.setenv("JIRA_USER_EMAIL", "bot@meridian.local")

    report = CapabilityReport(environment="test")
    executor = build_tool_executor(report)
    assert executor is not None
    assert "jira.lookup_status" in report.tools
    assert "jira.create_ticket" in report.tools
    assert executor.registry.names()  # at least one tool registered


def test_tool_executor_registers_slack_only_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from meridian_orchestrator.wiring import build_tool_executor

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-stub")
    report = CapabilityReport(environment="test")
    executor = build_tool_executor(report)
    assert executor is not None
    assert report.tools == ["slack.send_message"]
