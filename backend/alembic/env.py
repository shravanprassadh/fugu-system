"""Alembic environment for asynchronous Fugu database migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from fugu.boot.config import get_settings
from fugu.database.attachments import Attachment  # noqa: F401
from fugu.database.models import Base
from fugu.database.urls import sqlalchemy_asyncpg_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve one canonical SQLAlchemy asyncpg URL for every migration mode."""
    x_arguments = context.get_x_argument(as_dictionary=True)
    override = x_arguments.get("database_url")
    if override:
        return sqlalchemy_asyncpg_url(override)

    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url and "unused" not in configured_url:
        return sqlalchemy_asyncpg_url(configured_url)

    return sqlalchemy_asyncpg_url(get_settings().master_router_db_url)


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure and execute migrations on a synchronous connection facade."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations through an asynchronous SQLAlchemy engine."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
