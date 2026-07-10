"""Attachment route tests covering validation, ownership, retrieval, and deletion."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.api.dependencies import get_current_user
from fugu.api.routes.attachments import resolve_attachment_storage
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget, get_session_registry
from fugu.database.models import Base, User
from fugu.database.repositories import ThreadRepository, UserRepository
from fugu.main import create_app
from fugu.storage import AttachmentStorageConfig, LocalObjectStorage, get_attachment_storage_config
from tests.database_helpers import create_sqlite_engine_map


@dataclass
class AttachmentApiContext:
    registry: DatabaseSessionRegistry
    owner: User
    other: User
    thread_id: int
    storage: LocalObjectStorage
    config: AttachmentStorageConfig


@pytest_asyncio.fixture
async def attachment_api_context(tmp_path: Path) -> AsyncIterator[AttachmentApiContext]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async with registry.session(DatabaseTarget.MASTER) as session:
        owner = await UserRepository.add(session, username="file-owner", password_hash="hash", role="admin")
        other = await UserRepository.add(session, username="file-outsider", password_hash="hash")
        thread = await ThreadRepository.add(session, user_id=owner.id, name="Attachment API")
        thread_id = thread.id

    config = AttachmentStorageConfig(
        backend="local",
        bucket="test-attachments",
        local_root=tmp_path,
        max_file_size_bytes=1024,
    )
    yield AttachmentApiContext(
        registry=registry,
        owner=owner,
        other=other,
        thread_id=thread_id,
        storage=LocalObjectStorage(tmp_path),
        config=config,
    )
    await registry.dispose_pools()


def _client(context: AttachmentApiContext, user: User) -> AsyncClient:
    application: FastAPI = create_app()

    async def override_current_user() -> User:
        return user

    def override_registry() -> DatabaseSessionRegistry:
        return context.registry

    def override_storage() -> LocalObjectStorage:
        return context.storage

    def override_config() -> AttachmentStorageConfig:
        return context.config

    application.dependency_overrides[get_current_user] = override_current_user
    application.dependency_overrides[get_session_registry] = override_registry
    application.dependency_overrides[resolve_attachment_storage] = override_storage
    application.dependency_overrides[get_attachment_storage_config] = override_config
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


@pytest.mark.asyncio
async def test_attachment_upload_list_download_and_delete_are_owner_scoped(
    attachment_api_context: AttachmentApiContext,
) -> None:
    content = b"structured notes for the pipeline"
    async with _client(attachment_api_context, attachment_api_context.owner) as client:
        capabilities = await client.get("/api/attachments/capabilities")
        uploaded = await client.post(
            f"/api/threads/{attachment_api_context.thread_id}/attachments",
            files={"file": ("notes.txt", content, "text/plain")},
        )
        attachment_id = uploaded.json()["id"]
        listed = await client.get(f"/api/threads/{attachment_api_context.thread_id}/attachments")
        downloaded = await client.get(f"/api/attachments/{attachment_id}/content")

    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is True
    assert uploaded.status_code == 201
    assert uploaded.json()["upload_status"] == "uploaded"
    assert [item["id"] for item in listed.json()] == [attachment_id]
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    async with _client(attachment_api_context, attachment_api_context.other) as client:
        hidden = await client.get(f"/api/attachments/{attachment_id}")
        hidden_download = await client.get(f"/api/attachments/{attachment_id}/content")
    assert hidden.status_code == 404
    assert hidden_download.status_code == 404

    async with _client(attachment_api_context, attachment_api_context.owner) as client:
        deleted = await client.delete(f"/api/attachments/{attachment_id}")
        absent = await client.get(f"/api/attachments/{attachment_id}")
    assert deleted.status_code == 204
    assert absent.status_code == 404


@pytest.mark.asyncio
async def test_attachment_upload_rejects_unsupported_or_mismatched_files(
    attachment_api_context: AttachmentApiContext,
) -> None:
    async with _client(attachment_api_context, attachment_api_context.owner) as client:
        unsupported = await client.post(
            f"/api/threads/{attachment_api_context.thread_id}/attachments",
            files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
        )
        mismatched = await client.post(
            f"/api/threads/{attachment_api_context.thread_id}/attachments",
            files={"file": ("report.pdf", b"not a pdf", "application/pdf")},
        )
        oversized = await client.post(
            f"/api/threads/{attachment_api_context.thread_id}/attachments",
            files={"file": ("large.txt", b"x" * 1025, "text/plain")},
        )

    assert unsupported.status_code == 422
    assert mismatched.status_code == 422
    assert oversized.status_code == 422
