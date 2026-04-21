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
    assert heads == ["0002"], f"expected single head '0002', got {heads}"
    # And 0002 must reference 0001 so the chain is continuous.
    rev = script.get_revision("0002")
    assert rev is not None
    assert rev.down_revision == "0001"


def test_audit_log_indexes() -> None:
    table = Base.metadata.tables["audit_log"]
    index_names = {ix.name for ix in table.indexes}
    assert {"ix_audit_request", "ix_audit_user_ts", "ix_audit_event_type"}.issubset(index_names)
