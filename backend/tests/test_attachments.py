"""Tests for the Phase 5 attachment metadata foundation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.database.attachments import Attachment
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.exceptions import EntityNotFoundError
from fugu.database.models import Base
from fugu.database.repositories import AttachmentRepository, ThreadRepository, UserRepository
from fugu.storage import ObjectStorage, PresignedOperation, StoredObjectMetadata
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
        assert persisted.upload_status == "pending"
        listed = await AttachmentRepository.list_for_thread(
            session,
            thread_id=thread_id,
            owner_user_id=owner_id,
        )
        assert [item.public_id for item in listed] == [public_id]

        with pytest.raises(EntityNotFoundError, match="Attachment does not exist"):
            await AttachmentRepository.require_owned(
                session,
                public_id=public_id,
                owner_user_id=other_id,
            )


@pytest.mark.asyncio
async def test_attachment_lifecycle_preserves_metadata_without_binary_payload(
    session_registry: DatabaseSessionRegistry,
) -> None:
    async with session_registry.session(DatabaseTarget.MASTER) as session:
        owner = await UserRepository.add(session, username="lifecycle-owner", password_hash="hash")
        thread = await ThreadRepository.add(session, user_id=owner.id, name="Lifecycle thread")
        attachment = await AttachmentRepository.add_pending(
            session,
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
        assert attachment.expires_at is None
        await AttachmentRepository.mark_deleted(session, attachment=attachment)
        assert attachment.retention_status == "deleted"
        assert attachment.deleted_at is not None

    assert "binary" not in Attachment.__table__.columns
    assert "content" not in Attachment.__table__.columns
    assert {"storage_backend", "storage_bucket", "storage_key"}.issubset(Attachment.__table__.columns.keys())


def test_object_storage_contract_is_vendor_neutral() -> None:
    expected_methods = {"create_upload", "create_download", "inspect", "delete"}
    assert expected_methods.issubset(ObjectStorage.__protocol_attrs__)
    assert PresignedOperation.__dataclass_fields__["required_headers"]
    assert StoredObjectMetadata.__dataclass_fields__["size_bytes"]
