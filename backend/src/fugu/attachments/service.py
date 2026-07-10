"""Controlled attachment upload, retrieval, deletion, and cleanup."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from fugu.attachments.validation import ValidatedAttachment, validate_attachment
from fugu.database.attachments import Attachment
from fugu.database.repositories import AttachmentRepository
from fugu.storage.config import AttachmentStorageConfig
from fugu.storage.errors import AttachmentObjectNotFoundError, AttachmentStorageError
from fugu.storage.objects import ObjectStorage

_UPLOAD_EXPIRY_MINUTES = 15


class AttachmentService:
    """Coordinate relational metadata and private object storage through one ownership boundary."""

    def __init__(self, *, storage: ObjectStorage, config: AttachmentStorageConfig) -> None:
        self._storage = storage
        self._config = config

    async def upload(
        self,
        session: AsyncSession,
        *,
        owner_user_id: int,
        thread_id: int,
        filename: str,
        declared_mime_type: str | None,
        content: bytes,
    ) -> Attachment:
        validated = validate_attachment(
            filename=filename,
            declared_mime_type=declared_mime_type,
            content=content,
            max_file_size_bytes=self._config.max_file_size_bytes,
        )
        public_id = str(uuid4())
        storage_key = self._storage_key(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            public_id=public_id,
            validated=validated,
        )
        attachment = await AttachmentRepository.add_pending(
            session,
            public_id=public_id,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            original_filename=validated.filename,
            mime_type=validated.mime_type,
            file_extension=validated.extension,
            size_bytes=validated.size_bytes,
            sha256_hex=validated.sha256_hex,
            storage_backend=self._storage.backend_name,
            storage_bucket=self._config.bucket,
            storage_key=storage_key,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=_UPLOAD_EXPIRY_MINUTES),
        )
        try:
            stored = await self._storage.put(
                bucket=attachment.storage_bucket,
                key=attachment.storage_key,
                content=content,
                content_type=attachment.mime_type,
                checksum_sha256=attachment.sha256_hex,
            )
        except AttachmentStorageError:
            await AttachmentRepository.mark_upload_failed(session, attachment=attachment)
            raise
        if stored.size_bytes != attachment.size_bytes:
            await self._storage.delete(bucket=attachment.storage_bucket, key=attachment.storage_key)
            raise AttachmentStorageError("The stored attachment size does not match the validated upload.")
        if stored.checksum_sha256 and stored.checksum_sha256 != attachment.sha256_hex:
            await self._storage.delete(bucket=attachment.storage_bucket, key=attachment.storage_key)
            raise AttachmentStorageError("The stored attachment checksum does not match the validated upload.")
        return await AttachmentRepository.mark_uploaded(session, attachment=attachment)

    async def list_for_thread(
        self,
        session: AsyncSession,
        *,
        owner_user_id: int,
        thread_id: int,
    ) -> list[Attachment]:
        return await AttachmentRepository.list_for_thread(
            session,
            thread_id=thread_id,
            owner_user_id=owner_user_id,
        )

    async def require_owned(
        self,
        session: AsyncSession,
        *,
        owner_user_id: int,
        public_id: str,
    ) -> Attachment:
        return await AttachmentRepository.require_owned(
            session,
            public_id=public_id,
            owner_user_id=owner_user_id,
        )

    async def download(
        self,
        session: AsyncSession,
        *,
        owner_user_id: int,
        public_id: str,
    ) -> tuple[Attachment, bytes]:
        attachment = await self.require_owned(
            session,
            owner_user_id=owner_user_id,
            public_id=public_id,
        )
        if attachment.upload_status != "uploaded":
            raise AttachmentObjectNotFoundError("The attachment has not completed upload.")
        content = await self._storage.get(bucket=attachment.storage_bucket, key=attachment.storage_key)
        if len(content) != attachment.size_bytes or hashlib.sha256(content).hexdigest() != attachment.sha256_hex:
            raise AttachmentStorageError("The attachment object failed integrity verification.")
        return attachment, content

    async def delete(
        self,
        session: AsyncSession,
        *,
        owner_user_id: int,
        public_id: str,
    ) -> Attachment:
        attachment = await self.require_owned(
            session,
            owner_user_id=owner_user_id,
            public_id=public_id,
        )
        await self._storage.delete(bucket=attachment.storage_bucket, key=attachment.storage_key)
        return await AttachmentRepository.mark_deleted(session, attachment=attachment)

    async def cleanup_expired(self, session: AsyncSession, *, before: datetime | None = None) -> int:
        cutoff = before or datetime.now(timezone.utc)
        attachments = await AttachmentRepository.list_expired_pending(session, before=cutoff)
        for attachment in attachments:
            await self._storage.delete(bucket=attachment.storage_bucket, key=attachment.storage_key)
            await AttachmentRepository.mark_deleted(session, attachment=attachment, expired=True)
        return len(attachments)

    @staticmethod
    def _storage_key(
        *,
        owner_user_id: int,
        thread_id: int,
        public_id: str,
        validated: ValidatedAttachment,
    ) -> str:
        return (
            f"users/{owner_user_id}/threads/{thread_id}/attachments/{public_id}/"
            f"source.{validated.extension}"
        )
