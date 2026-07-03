"""Integration tests for asynchronous routing, transactions, and migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget
from fugu.database.exceptions import DatabaseRoutingError, QueryExecutionError
from fugu.database.models import Base
from fugu.database.repositories import ThreadRepository, UserRepository
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command
from alembic.config import Config


@pytest_asyncio.fixture
async def session_registry() -> AsyncIterator[DatabaseSessionRegistry]:
    """Create independent in-memory engines without requiring external PostgreSQL services."""
    engines: dict[DatabaseTarget, AsyncEngine] = {
        target: create_async_engine("sqlite+aiosqlite:///:memory:") for target in DatabaseTarget
    }
    registry = DatabaseSessionRegistry(engines)

    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    yield registry
    await registry.dispose_pools()


@pytest.mark.asyncio
async def test_workload_targets_use_independent_engines(
    session_registry: DatabaseSessionRegistry,
) -> None:
    """Each workload target must resolve to its own engine and pass readiness checks."""
    master_engine = session_registry.get_engine(DatabaseTarget.MASTER)
    metadata_engine = session_registry.get_engine(DatabaseTarget.METADATA)
    logs_engine = session_registry.get_engine(DatabaseTarget.LOGS)

    assert master_engine is not metadata_engine
    assert master_engine is not logs_engine
    assert metadata_engine is not logs_engine

    for target in DatabaseTarget:
        await session_registry.ping(target)


def test_unknown_workload_target_is_rejected(
    session_registry: DatabaseSessionRegistry,
) -> None:
    """Unregistered workload names must fail explicitly rather than falling back silently."""
    with pytest.raises(DatabaseRoutingError):
        session_registry.get_engine("unknown")


@pytest.mark.asyncio
async def test_successful_transaction_commits(
    session_registry: DatabaseSessionRegistry,
) -> None:
    """A successful unit of work must be visible to the next session."""
    async with session_registry.session(DatabaseTarget.MASTER) as session:
        user = await UserRepository.add(
            session,
            username="committed-user",
            password_hash="test-hash",
        )
        await ThreadRepository.add(session, user_id=user.id, name="Committed thread")

    async with session_registry.session(DatabaseTarget.MASTER) as session:
        persisted = await UserRepository.get_by_username(session, "committed-user")
        assert persisted is not None
        threads = await ThreadRepository.list_owned(session, user_id=persisted.id)
        assert [thread.name for thread in threads] == ["Committed thread"]


@pytest.mark.asyncio
async def test_application_error_rolls_back_transaction(
    session_registry: DatabaseSessionRegistry,
) -> None:
    """Application exceptions inside the context must not leave partial writes."""
    with pytest.raises(RuntimeError, match="abort transaction"):
        async with session_registry.session(DatabaseTarget.MASTER) as session:
            await UserRepository.add(
                session,
                username="rolled-back-user",
                password_hash="test-hash",
            )
            raise RuntimeError("abort transaction")

    async with session_registry.session(DatabaseTarget.MASTER) as session:
        persisted = await UserRepository.get_by_username(session, "rolled-back-user")
        assert persisted is None


@pytest.mark.asyncio
async def test_constraint_error_is_typed_and_rolled_back(
    session_registry: DatabaseSessionRegistry,
) -> None:
    """Constraint failures must become QueryExecutionError and preserve prior state."""
    async with session_registry.session(DatabaseTarget.MASTER) as session:
        await UserRepository.add(
            session,
            username="unique-user",
            password_hash="first-hash",
        )

    with pytest.raises(QueryExecutionError):
        async with session_registry.session(DatabaseTarget.MASTER) as session:
            await UserRepository.add(
                session,
                username="unique-user",
                password_hash="duplicate-hash",
            )

    async with session_registry.session(DatabaseTarget.MASTER) as session:
        persisted = await UserRepository.get_by_username(session, "unique-user")
        assert persisted is not None
        assert persisted.password_hash == "first-hash"


def test_alembic_upgrade_and_downgrade(tmp_path: Path) -> None:
    """The initial migration must create and remove the complete schema."""
    database_path = tmp_path / "migration-test.db"
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+aiosqlite:///{database_path}",
    )

    command.upgrade(alembic_config, "head")

    with sqlite3.connect(database_path) as connection:
        table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {
        "users",
        "threads",
        "messages",
        "provider_credentials",
        "pipeline_steps",
        "pipeline_runs",
        "pipeline_step_runs",
    }.issubset(table_names)

    command.downgrade(alembic_config, "base")

    with sqlite3.connect(database_path) as connection:
        remaining_tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert "users" not in remaining_tables
    assert "threads" not in remaining_tables
