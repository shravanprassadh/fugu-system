"""Serialized production schema migration runner."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

from fugu.boot.config import InfrastructureConfig, get_settings
from fugu.database.urls import asyncpg_dsn


class MigrationError(RuntimeError):
    """Base error for production migration orchestration failures."""


class MigrationLockTimeoutError(MigrationError):
    """Raised when another deployment holds the migration lock too long."""


class MigrationProcessError(MigrationError):
    """Raised when the Alembic subprocess exits unsuccessfully."""


def _resolve_alembic_config() -> Path:
    """Resolve Alembic configuration from the runtime working directory."""
    configured_path = os.getenv("ALEMBIC_CONFIG")
    candidate = Path(configured_path).expanduser() if configured_path else Path.cwd() / "alembic.ini"
    resolved_candidate = candidate.resolve()

    if not resolved_candidate.is_file():
        source = "ALEMBIC_CONFIG" if configured_path else "the current working directory"
        raise MigrationError(
            f"Could not find Alembic configuration at '{resolved_candidate}' resolved from {source}."
        )

    return resolved_candidate


async def run_schema_migrations(
    settings: InfrastructureConfig | None = None,
) -> None:
    """Acquire a cross-replica advisory lock and apply Alembic migrations."""
    resolved_settings = settings or get_settings()
    alembic_config = _resolve_alembic_config()
    backend_root = alembic_config.parent

    try:
        migration_dsn = asyncpg_dsn(resolved_settings.master_router_db_url)
    except ValueError as exc:
        raise MigrationError("The migration database URL is invalid for asyncpg.") from exc

    connection = await asyncpg.connect(
        dsn=migration_dsn,
        command_timeout=resolved_settings.network_request_timeout,
        timeout=resolved_settings.network_request_timeout,
    )
    lock_acquired = False

    try:
        try:
            await asyncio.wait_for(
                connection.fetchval(
                    "SELECT pg_advisory_lock($1)",
                    resolved_settings.migration_lock_id,
                ),
                timeout=resolved_settings.migration_lock_timeout_seconds,
            )
            lock_acquired = True
        except TimeoutError as exc:
            raise MigrationLockTimeoutError("Timed out waiting for the production schema migration lock.") from exc

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(alembic_config),
            "upgrade",
            "head",
            cwd=str(backend_root),
        )
        return_code = await process.wait()
        if return_code != 0:
            raise MigrationProcessError(f"Alembic exited with non-zero status {return_code}.")
    finally:
        if lock_acquired and not connection.is_closed():
            try:
                await connection.fetchval(
                    "SELECT pg_advisory_unlock($1)",
                    resolved_settings.migration_lock_id,
                )
            finally:
                await connection.close()
        elif not connection.is_closed():
            await connection.close()


def main() -> None:
    """Run migrations as a container entrypoint command."""
    asyncio.run(run_schema_migrations())


if __name__ == "__main__":
    main()
