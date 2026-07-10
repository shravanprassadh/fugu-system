"""Authenticated attachment upload, retrieval, deletion, and cleanup routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from fugu.api.dependencies import AdminUser, CurrentUser, MasterSession, OwnedThread
from fugu.attachments import AttachmentService, supported_extensions
from fugu.database.attachments import Attachment
from fugu.database.exceptions import EntityNotFoundError
from fugu.storage import (
    AttachmentObjectNotFoundError,
    AttachmentStorageConfig,
    AttachmentStorageError,
    AttachmentStorageUnavailableError,
    AttachmentValidationError,
    ObjectStorage,
    get_attachment_storage_config,
    get_object_storage,
)

attachments_router = APIRouter(tags=["attachments"])
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
StorageConfig = Annotated[AttachmentStorageConfig, Depends(get_attachment_storage_config)]


class AttachmentCapabilitiesResponse(BaseModel):
    """Public upload constraints for the authenticated chat interface."""

    enabled: bool
    max_file_size_bytes: int
    supported_extensions: tuple[str, ...]


class AttachmentResponse(BaseModel):
    """Non-sensitive attachment metadata returned to its owner."""

    id: str
    thread_id: int
    message_id: int | None
    filename: str
    mime_type: str
    extension: str
    size_bytes: int
    upload_status: str
    processing_status: str
    retention_status: str
    processing_error_code: str | None
    processing_error_message: str | None
    created_at: datetime
    uploaded_at: datetime | None
    processed_at: datetime | None

    @classmethod
    def from_attachment(cls, attachment: Attachment) -> AttachmentResponse:
        return cls(
            id=attachment.public_id,
            thread_id=attachment.thread_id,
            message_id=attachment.message_id,
            filename=attachment.original_filename,
            mime_type=attachment.mime_type,
            extension=attachment.file_extension,
            size_bytes=attachment.size_bytes,
            upload_status=attachment.upload_status,
            processing_status=attachment.processing_status,
            retention_status=attachment.retention_status,
            processing_error_code=attachment.processing_error_code,
            processing_error_message=attachment.processing_error_message,
            created_at=attachment.created_at,
            uploaded_at=attachment.uploaded_at,
            processed_at=attachment.processed_at,
        )


class AttachmentCleanupResponse(BaseModel):
    """Number of expired attachment records and objects removed."""

    cleaned: int


def _service(storage: ObjectStorage, config: AttachmentStorageConfig) -> AttachmentService:
    return AttachmentService(storage=storage, config=config)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AttachmentValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, EntityNotFoundError | AttachmentObjectNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    if isinstance(exc, AttachmentStorageUnavailableError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="The private attachment store could not complete the request.",
    )


@attachments_router.get("/api/attachments/capabilities", response_model=AttachmentCapabilitiesResponse)
async def attachment_capabilities(
    current_user: CurrentUser,
    config: StorageConfig,
) -> AttachmentCapabilitiesResponse:
    """Return file constraints without exposing object-store configuration."""
    del current_user
    return AttachmentCapabilitiesResponse(
        enabled=config.backend != "disabled",
        max_file_size_bytes=config.max_file_size_bytes,
        supported_extensions=supported_extensions(),
    )


@attachments_router.post(
    "/api/threads/{thread_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    thread: OwnedThread,
    session: MasterSession,
    storage: Storage,
    config: StorageConfig,
    file: Annotated[UploadFile, File(...)],
) -> AttachmentResponse:
    """Validate and store one file in a private object store for an owned thread."""
    try:
        content = await file.read(config.max_file_size_bytes + 1)
        attachment = await _service(storage, config).upload(
            session,
            owner_user_id=thread.user_id,
            thread_id=thread.id,
            filename=file.filename or "",
            declared_mime_type=file.content_type,
            content=content,
        )
        return AttachmentResponse.from_attachment(attachment)
    except (AttachmentValidationError, AttachmentStorageError, EntityNotFoundError) as exc:
        raise _http_error(exc) from exc
    finally:
        await file.close()


@attachments_router.get(
    "/api/threads/{thread_id}/attachments",
    response_model=list[AttachmentResponse],
)
async def list_thread_attachments(
    thread: OwnedThread,
    session: MasterSession,
    storage: Storage,
    config: StorageConfig,
) -> list[AttachmentResponse]:
    """List persistent attachment history for one owned thread."""
    attachments = await _service(storage, config).list_for_thread(
        session,
        owner_user_id=thread.user_id,
        thread_id=thread.id,
    )
    return [AttachmentResponse.from_attachment(attachment) for attachment in attachments]


@attachments_router.get("/api/attachments/{public_id}", response_model=AttachmentResponse)
async def get_attachment(
    public_id: str,
    current_user: CurrentUser,
    session: MasterSession,
    storage: Storage,
    config: StorageConfig,
) -> AttachmentResponse:
    """Return metadata only when the attachment belongs to the authenticated user."""
    try:
        attachment = await _service(storage, config).require_owned(
            session,
            owner_user_id=current_user.id,
            public_id=public_id,
        )
        return AttachmentResponse.from_attachment(attachment)
    except EntityNotFoundError as exc:
        raise _http_error(exc) from exc


@attachments_router.get("/api/attachments/{public_id}/content")
async def download_attachment(
    public_id: str,
    current_user: CurrentUser,
    session: MasterSession,
    storage: Storage,
    config: StorageConfig,
) -> Response:
    """Return integrity-verified private attachment bytes to their owner."""
    try:
        attachment, content = await _service(storage, config).download(
            session,
            owner_user_id=current_user.id,
            public_id=public_id,
        )
    except (EntityNotFoundError, AttachmentStorageError) as exc:
        raise _http_error(exc) from exc
    encoded_filename = quote(attachment.original_filename, safe="")
    return Response(
        content=content,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@attachments_router.delete(
    "/api/attachments/{public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_attachment(
    public_id: str,
    current_user: CurrentUser,
    session: MasterSession,
    storage: Storage,
    config: StorageConfig,
) -> Response:
    """Delete an owned object and hide its metadata without exposing storage paths."""
    try:
        await _service(storage, config).delete(
            session,
            owner_user_id=current_user.id,
            public_id=public_id,
        )
    except (EntityNotFoundError, AttachmentStorageError) as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@attachments_router.post("/api/admin/attachments/cleanup", response_model=AttachmentCleanupResponse)
async def cleanup_expired_attachments(
    admin_user: AdminUser,
    session: MasterSession,
    storage: Storage,
    config: StorageConfig,
) -> AttachmentCleanupResponse:
    """Remove expired pending objects and metadata through an administrator-only operation."""
    del admin_user
    try:
        cleaned = await _service(storage, config).cleanup_expired(session)
    except AttachmentStorageError as exc:
        raise _http_error(exc) from exc
    return AttachmentCleanupResponse(cleaned=cleaned)
