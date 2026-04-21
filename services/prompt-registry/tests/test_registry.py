"""Integration tests for the PromptRegistry — exercise immutability + rollback."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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
    NoPriorActivationError,
    PromptRegistry,
    PromptVersionNotFoundError,
)


def _template(name: str, body: str = "[SYSTEM] be helpful. [USER] {{query}}") -> PromptTemplate:
    return PromptTemplate(
        name=name,
        version=1,  # ignored by create_version
        model_tier=ModelTier.MID,
        min_model="claude-sonnet-4-6",
        template=body,
        parameters=["query"],
        schema_ref="generic_v1",
        few_shot_dataset=None,
        token_budget=TokenBudget(
            system=500, few_shot=0, retrieval=6000, history=2000, query=500, total_max=16000
        ),
        cache_control=CacheControl(breakpoints=["after_system"], prefix_stable=True),
        activation=ActivationInfo(
            environment="dev",
            status=ActivationStatus.DRAFT,
            canary_percentage=0,
            activated_at=datetime.now(tz=UTC),
            activated_by="tests@company.com",
        ),
    )


def test_create_version_auto_increments(registry: PromptRegistry) -> None:
    v1 = registry.create_version(_template("classifier"), created_by="a@x.com")
    v2 = registry.create_version(_template("classifier", body="v2"), created_by="a@x.com")
    v3 = registry.create_version(_template("classifier", body="v3"), created_by="a@x.com")
    assert (v1, v2, v3) == (1, 2, 3)

    versions = registry.list_versions("classifier")
    assert [t.version for t in versions] == [1, 2, 3]
    assert versions[2].template == "v3"


def test_get_version_raises_when_missing(registry: PromptRegistry) -> None:
    with pytest.raises(PromptVersionNotFoundError):
        registry.get_version("nope", 1)


def test_activate_archives_previous(registry: PromptRegistry) -> None:
    registry.create_version(_template("grounded_qa", body="v1"), created_by="a@x.com")
    registry.create_version(_template("grounded_qa", body="v2"), created_by="a@x.com")

    registry.activate("grounded_qa", 1, environment="prod", actor="alice@x.com")
    active = registry.get_active("grounded_qa", "prod")
    assert active.version == 1
    assert active.activation.status == ActivationStatus.ACTIVE

    registry.activate("grounded_qa", 2, environment="prod", actor="alice@x.com")
    active = registry.get_active("grounded_qa", "prod")
    assert active.version == 2
    assert active.activation.status == ActivationStatus.ACTIVE


def test_activate_with_canary_percentage(registry: PromptRegistry) -> None:
    registry.create_version(_template("classifier"), created_by="a@x.com")
    registry.activate(
        "classifier", 1, environment="prod", actor="alice@x.com", canary_percentage=25
    )
    active = registry.get_active("classifier", "prod")
    assert active.activation.status == ActivationStatus.CANARY
    assert active.activation.canary_percentage == 25


def test_activate_rejects_invalid_canary(registry: PromptRegistry) -> None:
    registry.create_version(_template("classifier"), created_by="a@x.com")
    with pytest.raises(ValueError):
        registry.activate(
            "classifier", 1, environment="prod", actor="a@x.com", canary_percentage=250
        )


def test_get_active_raises_before_first_activation(registry: PromptRegistry) -> None:
    registry.create_version(_template("classifier"), created_by="a@x.com")
    with pytest.raises(ActiveTemplateNotFoundError):
        registry.get_active("classifier", "prod")


def test_rollback_reverts_to_previous(registry: PromptRegistry) -> None:
    registry.create_version(_template("classifier", body="v1"), created_by="a@x.com")
    registry.create_version(_template("classifier", body="v2"), created_by="a@x.com")

    registry.activate("classifier", 1, environment="prod", actor="alice@x.com")
    registry.activate("classifier", 2, environment="prod", actor="alice@x.com")
    assert registry.get_active("classifier", "prod").version == 2

    new_active = registry.rollback("classifier", environment="prod", actor="bob@x.com")
    assert new_active == 1
    assert registry.get_active("classifier", "prod").version == 1


def test_rollback_raises_without_prior_activation(registry: PromptRegistry) -> None:
    registry.create_version(_template("classifier"), created_by="a@x.com")
    registry.activate("classifier", 1, environment="prod", actor="alice@x.com")
    with pytest.raises(NoPriorActivationError):
        registry.rollback("classifier", environment="prod", actor="bob@x.com")


def test_environments_are_isolated(registry: PromptRegistry) -> None:
    registry.create_version(_template("classifier", body="v1"), created_by="a@x.com")
    registry.create_version(_template("classifier", body="v2"), created_by="a@x.com")

    registry.activate("classifier", 1, environment="dev", actor="a@x.com")
    registry.activate("classifier", 2, environment="prod", actor="a@x.com")

    assert registry.get_active("classifier", "dev").version == 1
    assert registry.get_active("classifier", "prod").version == 2
