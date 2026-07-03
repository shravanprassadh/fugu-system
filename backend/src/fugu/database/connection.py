"""Asynchronous database engine routing and transaction management."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from enum import StrEnum
from functools import lru_cache
from typing import Never

from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fugu.boot.config import InfrastructureConfig, get_settings
from fugu.database.exceptions import (
    ConnectionPoolExhaustedError,
    DatabaseRoutingError,
    DatabaseUnavailableError,
    QueryExecutionError,
    TransactionRollbackError,
)


class DatabaseTarget(StrEnum):
    """Named workload targets with independent asynchronous connection pools."""

    MASTER = "master"
    METADATA = "metadata"
    LOGS = "logs"


def _normalize_asyncpg_url(url: object) -> str:
    """Return a SQLAlchemy-compatible asyncpg URL without mutating credentials."""
    normalized = str(url)
    if normalized.startswith("postgresql+asyncpg://"):
        return normalized
    if normalized.startswith("postgresql://"):
        return normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
    if normalized.startswith("postgres://"):
        return normalized.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError("Database URLs must use a PostgreSQL scheme.")


def _create_engine(url: object, settings: InfrastructureConfig) -> AsyncEngine:
    """Create one health-checked async engine from validated settings."""
    return create_async_engine(
        _normalize_asyncpg_url(url),
        pool_size=settings.db_pool_min_connections,
        max_overflow=settings.db_pool_max_connections - settings.db_pool_min_connections,
        pool_pre_ping=True,
        pool_timeout=settings.network_request_timeout,
    )


class DatabaseSessionRegistry:
    """Route workloads to independent engines and provide atomic session scopes."""

    def __init__(self, engines: Mapping[DatabaseTarget, AsyncEngine]) -> None:
        required_targets: set[DatabaseTarget] = set(DatabaseTarget)
        configured_targets: set[DatabaseTarget] = set(engines.keys())
        missing_targets = required_targets.difference(configured_targets)
        if missing_targets:
            missing = ", ".join(sorted(target.value for target in missing_targets))
            raise DatabaseRoutingError(f"Database engine mappings are missing required targets: {missing}.")

        self._engines: dict[DatabaseTarget, AsyncEngine] = dict(engines)
        self._sessionmakers: dict[DatabaseTarget, async_sessionmaker[AsyncSession]] = {
            target: async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
            for target, engine in self._engines.items()
        }

    @classmethod
    def from_settings(cls, settings: InfrastructureConfig) -> DatabaseSessionRegistry:
        """Construct one engine pool for each configured workload target."""
        engines: dict[DatabaseTarget, AsyncEngine] = {
            DatabaseTarget.MASTER: _create_engine(settings.master_router_db_url, settings),
            DatabaseTarget.METADATA: _create_engine(settings.metadata_sidebar_db_url, settings),
            DatabaseTarget.LOGS: _create_engine(settings.transactional_logs_db_url, settings),
        }
        return cls(engines)

    @staticmethod
    def _normalize_target(target: DatabaseTarget | str) -> DatabaseTarget:
        try:
            return target if isinstance(target, DatabaseTarget) else DatabaseTarget(target)
        except ValueError as exc:
            raise DatabaseRoutingError(f"Unknown database workload target: {target!r}.") from exc

    def get_engine(self, target: DatabaseTarget | str = DatabaseTarget.MASTER) -> AsyncEngine:
        """Return the engine assigned to a workload target."""
        normalized_target = self._normalize_target(target)
        return self._engines[normalized_target]

    async def _rollback_or_raise(
        self,
        session: AsyncSession,
        original_error: BaseException,
    ) -> Never:
        """Rollback a failed transaction and preserve rollback failures explicitly."""
        try:
            await session.rollback()
        except SQLAlchemyError as rollback_error:
            raise TransactionRollbackError("Database rollback failed after a transaction error.") from rollback_error
        raise original_error

    @asynccontextmanager
    async def session(
        self,
        target: DatabaseTarget | str = DatabaseTarget.MASTER,
    ) -> AsyncIterator[AsyncSession]:
        """Yield an async session, committing on success and rolling back on failure."""
        normalized_target = self._normalize_target(target)
        session = self._sessionmakers[normalized_target]()
        try:
            yield session
            await session.commit()
        except SQLAlchemyTimeoutError:
            await self._rollback_or_raise(
                session,
                ConnectionPoolExhaustedError(
                    f"Connection pool acquisition timed out for target {normalized_target.value!r}."
                ),
            )
        except (OperationalError, InterfaceError):
            await self._rollback_or_raise(
                session,
                DatabaseUnavailableError(
                    f"Database target {normalized_target.value!r} is unavailable."
                ),
            )
        except SQLAlchemyError:
            await self._rollback_or_raise(
                session,
                QueryExecutionError(
                    f"Database statement failed on target {normalized_target.value!r}."
                ),
            )
        except BaseException as exc:
            await self._rollback_or_raise(session, exc)
        finally:
            await session.close()

    async def ping(self, target: DatabaseTarget | str = DatabaseTarget.MASTER) -> None:
        """Verify connectivity without conflating an empty result set with failure."""
        normalized_target = self._normalize_target(target)
        engine = self._engines[normalized_target]
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyTimeoutError as exc:
            raise ConnectionPoolExhaustedError(
                f"Connection pool acquisition timed out for target {normalized_target.value!r}."
            ) from exc
        except (OperationalError, InterfaceError) as exc:
            raise DatabaseUnavailableError(
                f"Database target {normalized_target.value!r} is unavailable."
            ) from exc
        except SQLAlchemyError as exc:
            raise QueryExecutionError(
                f"Readiness query failed on target {normalized_target.value!r}."
            ) from exc

    async def dispose_pools(self) -> None:
        """Gracefully close all configured connection pools."""
        for engine in self._engines.values():
            await engine.dispose()


@lru_cache(maxsize=1)
def get_session_registry() -> DatabaseSessionRegistry:
    """Create the application registry lazily after settings validation succeeds."""
    return DatabaseSessionRegistry.from_settings(get_settings())
