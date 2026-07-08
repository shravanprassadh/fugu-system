"""Shared database helpers for backend integration tests."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fugu.database.connection import DatabaseTarget


def create_sqlite_async_engine() -> AsyncEngine:
    """Create an in-memory SQLite async engine with foreign-key cascades enabled.

    SQLite disables foreign-key enforcement by default. The production schema relies
    on database-level ``ON DELETE CASCADE`` constraints, so tests must enable the
    same constraint behavior explicitly or they will not exercise production-like
    deletion semantics.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def create_sqlite_engine_map() -> dict[DatabaseTarget, AsyncEngine]:
    """Create one isolated SQLite engine per configured database target."""
    return {target: create_sqlite_async_engine() for target in DatabaseTarget}
