"""Tests for the secure database-backed user bootstrap command."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.boot.create_user import (
    UserBootstrapError,
    create_database_user,
    validate_password,
    validate_role,
    validate_username,
)
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.models import Base
from fugu.database.repositories import UserRepository
from fugu.security.auth import IdentitySecurityManager
from tests.database_helpers import create_sqlite_engine_map

TEST_PASSWORD = "HighEntropyBootstrapPassword2026"


@pytest_asyncio.fixture
async def registry() -> AsyncIterator[DatabaseSessionRegistry]:
    """Provide isolated workload databases for bootstrap tests."""
    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    session_registry = DatabaseSessionRegistry(engines)

    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    try:
        yield session_registry
    finally:
        await session_registry.dispose_pools()


@pytest.mark.asyncio
async def test_create_database_user_hashes_and_persists_password(
    registry: DatabaseSessionRegistry,
) -> None:
    """The bootstrap path must persist an Argon2 hash rather than plaintext."""
    created = await create_database_user(
        registry,
        username="  administrator  ",
        password=TEST_PASSWORD,
        role="admin",
    )

    assert created.username == "administrator"
    assert created.role == "admin"
    assert created.password_hash != TEST_PASSWORD
    assert IdentitySecurityManager.verify_hash_match(TEST_PASSWORD, created.password_hash)

    async with registry.session(DatabaseTarget.MASTER) as session:
        persisted = await UserRepository.get_by_username(session, "administrator")

    assert persisted is not None
    assert persisted.id == created.id
    assert persisted.token_version == 0
    assert persisted.is_active is True


@pytest.mark.asyncio
async def test_create_database_user_rejects_duplicate_username(
    registry: DatabaseSessionRegistry,
) -> None:
    """An operator must not silently replace an existing account."""
    await create_database_user(
        registry,
        username="administrator",
        password=TEST_PASSWORD,
    )

    with pytest.raises(UserBootstrapError, match="already exists"):
        await create_database_user(
            registry,
            username="administrator",
            password="DifferentHighEntropyPassword2026",
        )


@pytest.mark.parametrize("username", ["", "ab", "x" * 256])
def test_validate_username_rejects_invalid_lengths(username: str) -> None:
    with pytest.raises(UserBootstrapError, match="between 3 and 255"):
        validate_username(username)


@pytest.mark.parametrize("password", ["short", "        ", "x" * 1_025])
def test_validate_password_rejects_invalid_values(password: str) -> None:
    with pytest.raises(UserBootstrapError):
        validate_password(password)


@pytest.mark.parametrize("role", ["owner", "superuser", ""])
def test_validate_role_rejects_unknown_roles(role: str) -> None:
    with pytest.raises(UserBootstrapError, match="either 'user' or 'admin'"):
        validate_role(role)
