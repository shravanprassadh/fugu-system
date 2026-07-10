"""Tests for attachment metadata, validation, and controlled object storage."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.attachments.validation import validate_attachment
from fugu.database.attachments import Attachment
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import Base
from fugu.database.repositories import AttachmentRepository, ThreadRepository, UserRepository
from fugu.storage import AttachmentValidationError, LocalObjectStorage, ObjectStorage, StoredObjectMetadata
from fugu.storage.errors import AttachmentStorageError
from tests.database_helpers import create_sqlite_engine_map


@pytest_asyncio.fixture
async def session_registry() -> AsyncIterator[DatabaseSessionRegistry]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield registry
    await registry.dispose_pools()


@pytest.mark.asyncio
async def test_attachment_repository_enforces_thread_and_record_ownership(
    session_registry: DatabaseSessionRegistry,
) -> None:
    async with session_registry.session(DatabaseTarget.MASTER) as session:
        owner = await UserRepository.add(session, username="attachment-owner", password_hash="hash")
        other = await UserRepository.add(session, username="attachment-other", password_hash="hash")
        thread = await ThreadRepository.add(session, user_id=owner.id, name="Document thread")
        attachment = await AttachmentRepository.add_pending(
            session,
            public_id="00000000-0000-4000-8000-000000000001",
            owner_user_id=owner.id,
            thread_id=thread.id,
            original_filename="report.pdf",
            mime_type="application/pdf",
            file_extension="pdf",
            size_bytes=2048,
            sha256_hex="a" * 64,
            storage_backend="s3-compatible",
            storage_bucket="fugu-attachments",
            storage_key=f"users/{owner.id}/threads/{thread.id}/report.pdf",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        public_id = attachment.public_id
        owner_id = owner.id
        other_id = other.id
        thread_id = thread.id

    async with session_registry.session(DatabaseTarget.MASTER) as session:
        persisted = await AttachmentRepository.require_owned(
            session,
            public_id=public_id,
            owner_user_id=owner_id,
        )
        assert persisted.original_filename == "report.pdf"
        listed = await AttachmentRepository.list_for_thread(
            session,
            thread_id=thread_id,
            owner_user_id=owner_id,
        )
        assert [item.public_id for item in listed] == [public_id]
        with pytest.raises(EntityNotFoundError, match="Attachment does not exist"):
            await AttachmentRepository.require_owned(session, public_id=public_id, owner_user_id=other_id)


@pytest.mark.asyncio
async def test_attachment_lifecycle_preserves_metadata_without_binary_payload(
    session_registry: DatabaseSessionRegistry,
) -> None:
    async with session_registry.session(DatabaseTarget.MASTER) as session:
        owner = await UserRepository.add(session, username="lifecycle-owner", password_hash="hash")
        thread = await ThreadRepository.add(session, user_id=owner.id, name="Lifecycle thread")
        attachment = await AttachmentRepository.add_pending(
            session,
            public_id="00000000-0000-4000-8000-000000000002",
            owner_user_id=owner.id,
            thread_id=thread.id,
            original_filename="image.png",
            mime_type="image/png",
            file_extension="png",
            size_bytes=512,
            sha256_hex="b" * 64,
            storage_backend="s3-compatible",
            storage_bucket="fugu-attachments",
            storage_key=f"users/{owner.id}/threads/{thread.id}/image.png",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        await AttachmentRepository.mark_uploaded(session, attachment=attachment)
        assert attachment.uploaded_at is not None
        await AttachmentRepository.mark_deleted(session, attachment=attachment)
        assert attachment.retention_status == "deleted"

    assert "binary" not in Attachment.__table__.columns
    assert "content" not in Attachment.__table__.columns
    assert {"storage_backend", "storage_bucket", "storage_key"}.issubset(Attachment.__table__.columns.keys())


def test_attachment_validation_rejects_mismatch_executable_and_oversize() -> None:
    validated = validate_attachment(
        filename="notes.txt",
        declared_mime_type="text/plain",
        content=b"hello world",
        max_file_size_bytes=100,
    )
    assert validated.extension == "txt"
    assert len(validated.sha256_hex) == 64

    with pytest.raises(AttachmentValidationError, match="MIME type"):
        validate_attachment(
            filename="report.pdf",
            declared_mime_type="text/plain",
            content=b"%PDF-1.7",
            max_file_size_bytes=100,
        )
    with pytest.raises(AttachmentValidationError, match="Executable"):
        validate_attachment(
            filename="malware.txt",
            declared_mime_type="text/plain",
            content=b"MZdanger",
            max_file_size_bytes=100,
        )
    with pytest.raises(AttachmentValidationError, match="upload limit"):
        validate_attachment(
            filename="large.txt",
            declared_mime_type="text/plain",
            content=b"x" * 101,
            max_file_size_bytes=100,
        )


@pytest.mark.asyncio
async def test_local_object_storage_is_private_integrity_checked_and_traversal_safe(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    content = b"private attachment"
    checksum = "f65d3b5f4b779a30d10b0f9f73db905a8b2a35c654a3dfc1c1aa19257c3ef4db"
    import hashlib

    checksum = hashlib.sha256(content).hexdigest()
    stored = await storage.put(
        bucket="bucket",
        key="users/1/attachment.txt",
        content=content,
        content_type="text/plain",
        checksum_sha256=checksum,
    )
    assert stored.checksum_sha256 == checksum
    assert await storage.get(bucket="bucket", key="users/1/attachment.txt") == content
    assert (await storage.inspect(bucket="bucket", key="users/1/attachment.txt")) is not None
    await storage.delete(bucket="bucket", key="users/1/attachment.txt")
    assert await storage.inspect(bucket="bucket", key="users/1/attachment.txt") is None

    with pytest.raises(AttachmentStorageError, match="escaped"):
        await storage.put(
            bucket="bucket",
            key="../../outside.txt",
            content=content,
            content_type="text/plain",
            checksum_sha256=checksum,
        )


def test_object_storage_contract_is_vendor_neutral() -> None:
    expected_methods = {"put", "get", "inspect", "delete"}
    assert all(callable(getattr(ObjectStorage, method, None)) for method in expected_methods)
    assert StoredObjectMetadata.__dataclass_fields__["size_bytes"]
