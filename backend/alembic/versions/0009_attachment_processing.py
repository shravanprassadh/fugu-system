"""Add structured attachment processing results and immutable run snapshots.

Revision ID: 0009_attachment_processing
Revises: 0008_attachment_foundation
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_attachment_processing"
down_revision: str | None = "0008_attachment_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("structured_content", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "attachments",
        sa.Column("processing_warnings", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column("attachments", sa.Column("processing_version", sa.String(length=50), nullable=True))
    op.add_column(
        "pipeline_runs",
        sa.Column("attachment_snapshot", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "attachment_snapshot")
    op.drop_column("attachments", "processing_version")
    op.drop_column("attachments", "processing_warnings")
    op.drop_column("attachments", "structured_content")
