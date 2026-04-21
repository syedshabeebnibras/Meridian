"""initial schema — prompt registry, eval results, audit log, pgvector

Revision ID: 0001
Revises:
Create Date: 2026-04-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Required extensions ----------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # prompt_templates -------------------------------------------------------
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("model_tier", sa.String(16), nullable=False),
        sa.Column("min_model", sa.String(128), nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("parameters", postgresql.JSONB, nullable=False),
        sa.Column("schema_ref", sa.String(128), nullable=False),
        sa.Column("few_shot_dataset", sa.String(128)),
        sa.Column("token_budget", postgresql.JSONB, nullable=False),
        sa.Column("cache_control", postgresql.JSONB, nullable=False),
        sa.Column("eval_results", postgresql.JSONB),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_prompt_name_version"),
        sa.CheckConstraint("version >= 1", name="ck_prompt_version_pos"),
    )
    op.create_index("ix_prompt_templates_name", "prompt_templates", ["name"])

    # prompt_activations -----------------------------------------------------
    op.create_table(
        "prompt_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("canary_percentage", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("activated_by", sa.String(256), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "canary_percentage BETWEEN 0 AND 100",
            name="ck_activation_canary_range",
        ),
    )
    op.create_index(
        "ix_prompt_activations_env_status",
        "prompt_activations",
        ["environment", "status"],
    )

    # eval_results -----------------------------------------------------------
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("eval_id", sa.String(128), nullable=False, unique=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("eval_type", sa.String(32), nullable=False),
        sa.Column("scores", postgresql.JSONB, nullable=False),
        sa.Column("judge_model", sa.String(128), nullable=False),
        sa.Column("judge_prompt_version", sa.String(128), nullable=False),
        sa.Column("golden_answer", sa.Text),
        sa.Column("human_label", sa.Text),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompt_version", sa.String(128), nullable=False),
        sa.Column("model_used", sa.String(128), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("passed", sa.Boolean),
    )
    op.create_index("ix_eval_results_request", "eval_results", ["request_id"])
    op.create_index(
        "ix_eval_results_type_ts", "eval_results", ["eval_type", "timestamp"]
    )
    op.create_index(
        "ix_eval_results_prompt_version", "eval_results", ["prompt_version"]
    )

    # audit_log --------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128)),
        sa.Column("session_id", sa.String(128)),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_request", "audit_log", ["request_id"])
    op.create_index("ix_audit_user_ts", "audit_log", ["user_id", "created_at"])
    op.create_index("ix_audit_event_type", "audit_log", ["event_type"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("eval_results")
    op.drop_table("prompt_activations")
    op.drop_table("prompt_templates")
    # Keep the extensions — they may be used by other tenants on the cluster.
