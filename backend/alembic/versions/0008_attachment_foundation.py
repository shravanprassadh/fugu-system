"""Add persistent attachment metadata.

Revision ID: 0008_attachment_foundation
Revises: 0007_execution_operability
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_attachment_foundation"
down_revision: str | None = "0007_execution_operability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_extension", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_hex", sa.String(length=64), nullable=False),
        sa.Column("storage_backend", sa.String(length=50), nullable=False),
        sa.Column("storage_bucket", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("upload_status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("processing_status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("retention_status", sa.String(length=50), server_default="active", nullable=False),
        sa.Column("processing_error_code", sa.String(length=100), nullable=True),
        sa.Column("processing_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_attachments_attachment_nonnegative_size")),
        sa.CheckConstraint("length(sha256_hex) = 64", name=op.f("ck_attachments_attachment_sha256_length")),
        sa.CheckConstraint(
            "upload_status IN ('pending', 'uploading', 'uploaded', 'failed', 'expired')",
            name=op.f("ck_attachments_attachment_upload_status"),
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'ready', 'failed', 'unsupported')",
            name=op.f("ck_attachments_attachment_processing_status"),
        ),
        sa.CheckConstraint(
            "retention_status IN ('active', 'deleting', 'deleted', 'expired')",
            name=op.f("ck_attachments_attachment_retention_status"),
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint(
            "storage_backend",
            "storage_bucket",
            "storage_key",
            name=op.f("uq_attachments_storage_backend"),
        ),
    )
    op.create_index("ix_attachments_owner_user_id", "attachments", ["owner_user_id"], unique=False)
    op.create_index("ix_attachments_thread_id", "attachments", ["thread_id"], unique=False)
    op.create_index("ix_attachments_message_id", "attachments", ["message_id"], unique=False)
    op.create_index("ix_attachments_owner_created", "attachments", ["owner_user_id", "created_at"], unique=False)
    op.create_index("ix_attachments_thread_created", "attachments", ["thread_id", "created_at"], unique=False)
    op.create_index("ix_attachments_upload_expiry", "attachments", ["upload_status", "expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_attachments_upload_expiry", table_name="attachments")
    op.drop_index("ix_attachments_thread_created", table_name="attachments")
    op.drop_index("ix_attachments_owner_created", table_name="attachments")
    op.drop_index("ix_attachments_message_id", table_name="attachments")
    op.drop_index("ix_attachments_thread_id", table_name="attachments")
    op.drop_index("ix_attachments_owner_user_id", table_name="attachments")
    op.drop_table("attachments")
