"""Serialized production schema migration runner."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

from fugu.boot.config import InfrastructureConfig, get_settings


class MigrationError(RuntimeError):
    """Base error for production migration orchestration failures."""


class MigrationConnectionError(MigrationError):
    """Raised when the migration database cannot be reached within the configured timeout."""


class MigrationLockTimeoutError(MigrationError):
    """Raised when another deployment holds the migration lock too long."""


class MigrationProcessError(MigrationError):
    """Raised when the Alembic subprocess exits unsuccessfully."""


def _asyncpg_dsn(database_url: object) -> str:
    """Convert a SQLAlchemy async URL into an asyncpg-compatible DSN."""
    dsn = str(database_url)
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    if dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        return dsn
    raise MigrationError("The migration database URL must use a PostgreSQL scheme.")


async def run_schema_migrations(
    settings: InfrastructureConfig | None = None,
) -> None:
    """Acquire a cross-replica advisory lock and apply Alembic migrations."""
    resolved_settings = settings or get_settings()
    backend_root = Path(__file__).resolve().parents[3]
    alembic_config = backend_root / "alembic.ini"

    print(
        "INFO: Connecting to the migration database.",
        file=sys.stderr,
        flush=True,
    )
    try:
        connection = await asyncpg.connect(
            dsn=_asyncpg_dsn(resolved_settings.master_router_db_url),
            command_timeout=resolved_settings.network_request_timeout,
            timeout=resolved_settings.network_request_timeout,
        )
    except (TimeoutError, OSError, asyncpg.PostgresError) as exc:
        raise MigrationConnectionError(
            "Could not connect to the migration database within the configured network timeout."
        ) from exc

    print(
        "INFO: Migration database connection established; acquiring advisory lock.",
        file=sys.stderr,
        flush=True,
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
            raise MigrationLockTimeoutError(
                "Timed out waiting for the production schema migration lock."
            ) from exc

        print(
            "INFO: Migration advisory lock acquired; running Alembic.",
            file=sys.stderr,
            flush=True,
        )
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
