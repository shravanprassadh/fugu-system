"""Thread CRUD route tests covering ownership isolation and lifecycle behavior."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.api.dependencies import get_current_user
from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.models import Base, Message, Thread, User
from fugu.database.repositories import (
    MessageRepository,
    ThreadRepository,
    UserRepository,
)
from fugu.main import create_app
from tests.database_helpers import create_sqlite_engine_map


@dataclass
class ThreadApiContext:
    """Isolated database registry and seeded identities for route tests."""

    registry: DatabaseSessionRegistry
    owner: User
    other_user: User
    thread_id: int


@pytest_asyncio.fixture
async def thread_api_context() -> AsyncIterator[ThreadApiContext]:
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    master_engine = registry.get_engine(DatabaseTarget.MASTER)
    async with master_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with registry.session(DatabaseTarget.MASTER) as session:
        owner = await UserRepository.add(session, username="thread-owner", password_hash="test-hash")
        other_user = await UserRepository.add(session, username="thread-outsider", password_hash="test-hash")
        thread = await ThreadRepository.add(session, user_id=owner.id, name="Seeded thread")
        await MessageRepository.add(
            session,
            thread_id=thread.id,
            user_id=owner.id,
            role="user",
            content="seeded user prompt",
        )
        await MessageRepository.add(
            session,
            thread_id=thread.id,
            user_id=owner.id,
            role="assistant",
            content="seeded assistant reply",
        )
        thread_id = thread.id

    yield ThreadApiContext(
        registry=registry,
        owner=owner,
        other_user=other_user,
        thread_id=thread_id,
    )
    await registry.dispose_pools()


def _build_client(context: ThreadApiContext, acting_user: User) -> AsyncClient:
    application: FastAPI = create_app()

    async def override_current_user() -> User:
        return acting_user

    def override_registry() -> DatabaseSessionRegistry:
        return context.registry

    application.dependency_overrides[get_current_user] = override_current_user
    application.dependency_overrides[get_session_registry] = override_registry
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


@pytest.mark.asyncio
async def test_thread_listing_returns_only_owned_threads(
    thread_api_context: ThreadApiContext,
) -> None:
    async with _build_client(thread_api_context, thread_api_context.owner) as client:
        owner_response = await client.get("/api/threads")
    async with _build_client(thread_api_context, thread_api_context.other_user) as client:
        outsider_response = await client.get("/api/threads")

    assert owner_response.status_code == 200
    owned = owner_response.json()
    assert [thread["name"] for thread in owned] == ["Seeded thread"]
    assert {"id", "name", "created_at"}.issubset(owned[0].keys())

    assert outsider_response.status_code == 200
    assert outsider_response.json() == []


@pytest.mark.asyncio
async def test_thread_creation_persists_a_normalized_name(
    thread_api_context: ThreadApiContext,
) -> None:
    async with _build_client(thread_api_context, thread_api_context.owner) as client:
        created = await client.post("/api/threads", json={"name": "  Quarterly analysis  "})
        rejected = await client.post("/api/threads", json={"name": "   "})

    assert created.status_code == 201
    assert created.json()["name"] == "Quarterly analysis"
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_message_history_is_scoped_to_the_owning_user(
    thread_api_context: ThreadApiContext,
) -> None:
    async with _build_client(thread_api_context, thread_api_context.owner) as client:
        owner_response = await client.get(f"/api/threads/{thread_api_context.thread_id}/messages")
    async with _build_client(thread_api_context, thread_api_context.other_user) as client:
        outsider_response = await client.get(f"/api/threads/{thread_api_context.thread_id}/messages")

    assert owner_response.status_code == 200
    history = owner_response.json()
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert history[0]["content"] == "seeded user prompt"

    assert outsider_response.status_code == 404


@pytest.mark.asyncio
async def test_thread_rename_updates_only_owned_threads(
    thread_api_context: ThreadApiContext,
) -> None:
    async with _build_client(thread_api_context, thread_api_context.owner) as client:
        renamed = await client.patch(
            f"/api/threads/{thread_api_context.thread_id}",
            json={"name": "Renamed thread"},
        )
    async with _build_client(thread_api_context, thread_api_context.other_user) as client:
        forbidden = await client.patch(
            f"/api/threads/{thread_api_context.thread_id}",
            json={"name": "Hijacked"},
        )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed thread"
    assert forbidden.status_code == 404

    async with thread_api_context.registry.session(DatabaseTarget.MASTER) as session:
        thread = await ThreadRepository.require_owned(
            session,
            thread_id=thread_api_context.thread_id,
            user_id=thread_api_context.owner.id,
        )
        assert thread.name == "Renamed thread"


@pytest.mark.asyncio
async def test_thread_deletion_cascades_and_respects_ownership(
    thread_api_context: ThreadApiContext,
) -> None:
    async with _build_client(thread_api_context, thread_api_context.other_user) as client:
        forbidden = await client.delete(f"/api/threads/{thread_api_context.thread_id}")
    async with _build_client(thread_api_context, thread_api_context.owner) as client:
        deleted = await client.delete(f"/api/threads/{thread_api_context.thread_id}")

    assert forbidden.status_code == 404
    assert deleted.status_code == 204

    async with thread_api_context.registry.session(DatabaseTarget.MASTER) as session:
        remaining_threads = await session.scalar(select(func.count()).select_from(Thread))
        remaining_messages = await session.scalar(select(func.count()).select_from(Message))
        assert remaining_threads == 0
        assert remaining_messages == 0
