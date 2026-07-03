"""Add authentication invalidation and pipeline-run identity constraints.

Revision ID: 0002_auth_and_run_integrity
Revises: 0001_initial_schema
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_and_run_integrity"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Bring the initial database schema into alignment with current models."""
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_user_token_version",
        "users",
        "token_version >= 0",
    )
    op.create_unique_constraint(
        "pipeline_step_run_identity",
        "pipeline_step_runs",
        ["run_id", "step_name"],
    )


def downgrade() -> None:
    """Remove authentication invalidation and run-identity enforcement."""
    op.drop_constraint(
        "pipeline_step_run_identity",
        "pipeline_step_runs",
        type_="unique",
    )
    op.drop_constraint(
        "ck_users_user_token_version",
        "users",
        type_="check",
    )
    op.drop_column("users", "token_version")
