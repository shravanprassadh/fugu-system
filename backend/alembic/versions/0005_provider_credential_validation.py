"""Add provider credential validation history.

Revision ID: 0005_provider_credential_validation
Revises: 0004_thread_memories
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_provider_credential_validation"
down_revision: str | None = "0004_thread_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_credentials",
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_credentials",
        sa.Column("last_successful_test_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_credentials",
        sa.Column("last_test_failure_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_credentials",
        sa.Column("last_test_failure_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_credentials", "last_test_failure_message")
    op.drop_column("provider_credentials", "last_test_failure_at")
    op.drop_column("provider_credentials", "last_successful_test_at")
    op.drop_column("provider_credentials", "last_tested_at")
