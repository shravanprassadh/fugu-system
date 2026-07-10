"""Add execution diagnostics, cancellation, and retry lineage.

Revision ID: 0007_execution_operability
Revises: 0006_versioned_pipeline_control
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_execution_operability"
down_revision: str | None = "0006_versioned_pipeline_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_pipeline_runs_pipeline_run_status", "pipeline_runs", type_="check")
    op.add_column("pipeline_runs", sa.Column("requested_by_user_id", sa.Integer(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("source_run_id", sa.Integer(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("retry_kind", sa.String(length=50), nullable=True))
    op.add_column("pipeline_runs", sa.Column("retry_stage_name", sa.String(length=100), nullable=True))
    op.add_column("pipeline_runs", sa.Column("initial_prompt_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "pipeline_runs",
        sa.Column("request_options", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column("pipeline_runs", sa.Column("failed_stage", sa.String(length=100), nullable=True))
    op.add_column("pipeline_runs", sa.Column("error_category", sa.String(length=100), nullable=True))
    op.add_column("pipeline_runs", sa.Column("retryable", sa.Boolean(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("final_result_trace", sa.Text(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pipeline_runs", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_pipeline_runs_requested_by_user_id_users"),
        "pipeline_runs",
        "users",
        ["requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_pipeline_runs_source_run_id_pipeline_runs"),
        "pipeline_runs",
        "pipeline_runs",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_pipeline_runs_requested_by_user_id", "pipeline_runs", ["requested_by_user_id"], unique=False)
    op.create_index("ix_pipeline_runs_source_run_id", "pipeline_runs", ["source_run_id"], unique=False)
    op.create_index("ix_pipeline_runs_status_created", "pipeline_runs", ["status", "created_at"], unique=False)
    op.create_check_constraint(
        "ck_pipeline_runs_pipeline_run_status",
        "pipeline_runs",
        "status IN ('pending', 'running', 'cancelling', 'cancelled', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_pipeline_runs_pipeline_run_retry_kind",
        "pipeline_runs",
        "retry_kind IS NULL OR retry_kind IN ('whole_run', 'stage')",
    )
    op.execute(
        sa.text(
            "UPDATE pipeline_runs SET requested_by_user_id = threads.user_id "
            "FROM threads WHERE pipeline_runs.thread_id = threads.id"
        )
    )

    op.drop_constraint("ck_pipeline_step_runs_pipeline_step_run_status", "pipeline_step_runs", type_="check")
    op.add_column("pipeline_step_runs", sa.Column("provider_type", sa.String(length=100), nullable=True))
    op.add_column("pipeline_step_runs", sa.Column("model_string", sa.String(length=255), nullable=True))
    op.add_column("pipeline_step_runs", sa.Column("input_trace", sa.Text(), nullable=True))
    op.add_column(
        "pipeline_step_runs",
        sa.Column("retry_attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("pipeline_step_runs", sa.Column("input_token_usage", sa.Integer(), nullable=True))
    op.add_column("pipeline_step_runs", sa.Column("output_token_usage", sa.Integer(), nullable=True))
    op.add_column("pipeline_step_runs", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column(
        "pipeline_step_runs",
        sa.Column("side_effect_free", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column("pipeline_step_runs", sa.Column("error_code", sa.String(length=100), nullable=True))
    op.add_column("pipeline_step_runs", sa.Column("error_category", sa.String(length=100), nullable=True))
    op.add_column("pipeline_step_runs", sa.Column("retryable", sa.Boolean(), nullable=True))
    op.create_check_constraint(
        "ck_pipeline_step_runs_pipeline_step_run_status",
        "pipeline_step_runs",
        "status IN ('pending', 'running', 'cancelled', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_pipeline_step_runs_pipeline_step_run_nonnegative_retry_attempts",
        "pipeline_step_runs",
        "retry_attempt_count >= 0",
    )
    op.create_check_constraint(
        "ck_pipeline_step_runs_pipeline_step_run_nonnegative_latency",
        "pipeline_step_runs",
        "latency_ms IS NULL OR latency_ms >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_pipeline_step_runs_pipeline_step_run_nonnegative_latency",
        "pipeline_step_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_pipeline_step_runs_pipeline_step_run_nonnegative_retry_attempts",
        "pipeline_step_runs",
        type_="check",
    )
    op.drop_constraint("ck_pipeline_step_runs_pipeline_step_run_status", "pipeline_step_runs", type_="check")
    op.create_check_constraint(
        "ck_pipeline_step_runs_pipeline_step_run_status",
        "pipeline_step_runs",
        "status IN ('pending', 'running', 'completed', 'failed')",
    )
    for column_name in (
        "retryable",
        "error_category",
        "error_code",
        "side_effect_free",
        "latency_ms",
        "output_token_usage",
        "input_token_usage",
        "retry_attempt_count",
        "input_trace",
        "model_string",
        "provider_type",
    ):
        op.drop_column("pipeline_step_runs", column_name)

    op.drop_constraint("ck_pipeline_runs_pipeline_run_retry_kind", "pipeline_runs", type_="check")
    op.drop_constraint("ck_pipeline_runs_pipeline_run_status", "pipeline_runs", type_="check")
    op.create_check_constraint(
        "ck_pipeline_runs_pipeline_run_status",
        "pipeline_runs",
        "status IN ('pending', 'running', 'completed', 'failed')",
    )
    op.drop_index("ix_pipeline_runs_status_created", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_source_run_id", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_requested_by_user_id", table_name="pipeline_runs")
    op.drop_constraint(op.f("fk_pipeline_runs_source_run_id_pipeline_runs"), "pipeline_runs", type_="foreignkey")
    op.drop_constraint(op.f("fk_pipeline_runs_requested_by_user_id_users"), "pipeline_runs", type_="foreignkey")
    for column_name in (
        "cancelled_at",
        "cancellation_requested_at",
        "final_result_trace",
        "retryable",
        "error_category",
        "failed_stage",
        "request_options",
        "initial_prompt_snapshot",
        "retry_stage_name",
        "retry_kind",
        "source_run_id",
        "requested_by_user_id",
    ):
        op.drop_column("pipeline_runs", column_name)
