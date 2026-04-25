"""DB-free sanity checks for the ORM metadata and Alembic script graph."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from meridian_db import Base

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_all_expected_tables_registered() -> None:
    expected = {
        "prompt_templates",
        "prompt_activations",
        "eval_results",
        "audit_log",
        "few_shot_examples",
        "prompt_audit_log",
        # Phase 2 tenant + auth layer
        "users",
        "workspaces",
        "memberships",
        "chat_sessions",
        "chat_messages",
        "feedback_records",
        "audit_events",
        "usage_records",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_prompt_templates_constraints_present() -> None:
    table = Base.metadata.tables["prompt_templates"]
    constraint_names = {c.name for c in table.constraints if c.name is not None}
    assert "uq_prompt_name_version" in constraint_names
    assert "ck_prompt_version_pos" in constraint_names


def test_alembic_script_graph_loads() -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    assert heads == ["0007"], f"expected single head '0007', got {heads}"
    # The migration chain must be continuous all the way back.
    for rev_id, down_id in (
        ("0007", "0006"),
        ("0006", "0005"),
        ("0005", "0004"),
        ("0004", "0003"),
        ("0003", "0002"),
        ("0002", "0001"),
    ):
        rev = script.get_revision(rev_id)
        assert rev is not None and rev.down_revision == down_id, (
            f"{rev_id} must descend from {down_id}"
        )


def test_audit_log_indexes() -> None:
    table = Base.metadata.tables["audit_log"]
    index_names = {ix.name for ix in table.indexes}
    assert {"ix_audit_request", "ix_audit_user_ts", "ix_audit_event_type"}.issubset(index_names)
