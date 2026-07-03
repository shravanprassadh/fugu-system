"""Enforce one trace row per step within a pipeline run.

Revision ID: 0003_pipeline_step_run_identity
Revises: 0002_user_token_version
Create Date: 2026-07-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_pipeline_step_run_identity"
down_revision: str | None = "0002_user_token_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pipeline_step_runs") as batch_op:
        batch_op.create_unique_constraint(
            "pipeline_step_run_identity",
            ["run_id", "step_name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("pipeline_step_runs") as batch_op:
        batch_op.drop_constraint(
            "pipeline_step_run_identity",
            type_="unique",
        )
