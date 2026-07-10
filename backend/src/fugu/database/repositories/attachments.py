"""Ownership-scoped persistence operations for attachment metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.database.attachments import Attachment
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.repositories.core import ThreadRepository


class AttachmentRepository:
    """Persist attachment metadata without exposing cross-user records."""

    @staticmethod
    async def add_pending(
        session: AsyncSession,
        *,
        owner_user_id: int,
        thread_id: int,
        original_filename: str,
        mime_type: str,
        file_extension: str,
        size_bytes: int,
        sha256_hex: str,
        storage_backend: str,
        storage_bucket: str,
        storage_key: str,
        expires_at: datetime,
    ) -> Attachment:
        await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=owner_user_id)
        attachment = Attachment(
            public_id=str(uuid4()),
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            original_filename=original_filename,
            mime_type=mime_type,
            file_extension=file_extension,
            size_bytes=size_bytes,
            sha256_hex=sha256_hex,
            storage_backend=storage_backend,
            storage_bucket=storage_bucket,
            storage_key=storage_key,
            expires_at=expires_at,
        )
        session.add(attachment)
        await session.flush()
        return attachment

    @staticmethod
    async def get_owned(session: AsyncSession, *, public_id: str, owner_user_id: int) -> Attachment | None:
        statement = select(Attachment).where(
            Attachment.public_id == public_id,
            Attachment.owner_user_id == owner_user_id,
            Attachment.retention_status != "deleted",
        )
        result = await session.scalars(statement)
        return result.one_or_none()

    @staticmethod
    async def require_owned(session: AsyncSession, *, public_id: str, owner_user_id: int) -> Attachment:
        attachment = await AttachmentRepository.get_owned(
            session,
            public_id=public_id,
            owner_user_id=owner_user_id,
        )
        if attachment is None:
            raise EntityNotFoundError("Attachment does not exist within the authenticated user's scope.")
        return attachment

    @staticmethod
    async def list_for_thread(
        session: AsyncSession,
        *,
        thread_id: int,
        owner_user_id: int,
    ) -> list[Attachment]:
        await ThreadRepository.require_owned(session, thread_id=thread_id, user_id=owner_user_id)
        statement = (
            select(Attachment)
            .where(
                Attachment.thread_id == thread_id,
                Attachment.owner_user_id == owner_user_id,
                Attachment.retention_status != "deleted",
            )
            .order_by(Attachment.created_at.asc())
        )
        result = await session.scalars(statement)
        return list(result.all())

    @staticmethod
    async def mark_uploaded(session: AsyncSession, *, attachment: Attachment) -> Attachment:
        attachment.upload_status = "uploaded"
        attachment.uploaded_at = datetime.now(timezone.utc)
        attachment.expires_at = None
        await session.flush()
        return attachment

    @staticmethod
    async def link_message(
        session: AsyncSession,
        *,
        attachment: Attachment,
        message_id: int,
    ) -> Attachment:
        attachment.message_id = message_id
        await session.flush()
        return attachment

    @staticmethod
    async def mark_deleted(session: AsyncSession, *, attachment: Attachment) -> Attachment:
        attachment.retention_status = "deleted"
        attachment.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        return attachment
