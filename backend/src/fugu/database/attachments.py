"""Persistent attachment metadata; binary objects remain outside PostgreSQL."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fugu.database.models import Base


class Attachment(Base):
    """One user-owned file associated with a conversation thread."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    upload_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", server_default="pending")
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    retention_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        server_default="active",
    )
    processing_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processing_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="attachment_nonnegative_size"),
        CheckConstraint("length(sha256_hex) = 64", name="attachment_sha256_length"),
        CheckConstraint(
            "upload_status IN ('pending', 'uploading', 'uploaded', 'failed', 'expired')",
            name="attachment_upload_status",
        ),
        CheckConstraint(
            "processing_status IN ('pending', 'processing', 'ready', 'failed', 'unsupported')",
            name="attachment_processing_status",
        ),
        CheckConstraint(
            "retention_status IN ('active', 'deleting', 'deleted', 'expired')",
            name="attachment_retention_status",
        ),
        UniqueConstraint("storage_backend", "storage_bucket", "storage_key", name="attachment_storage_object"),
        Index("ix_attachments_owner_created", "owner_user_id", "created_at"),
        Index("ix_attachments_thread_created", "thread_id", "created_at"),
        Index("ix_attachments_upload_expiry", "upload_status", "expires_at"),
    )
