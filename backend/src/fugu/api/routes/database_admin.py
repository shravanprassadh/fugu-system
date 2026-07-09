# ruff: noqa: I001
"""Database connection administration routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, status
from fugu.api.dependencies import AdminUser
from fugu.boot.config import get_settings
from fugu.database.connection import DatabaseTarget, get_session_registry
from fugu.database.urls import sqlalchemy_asyncpg_url
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


database_admin_router = APIRouter(prefix="/api/admin/database", tags=["database-administration"])

_TARGET_LABELS: dict[DatabaseTarget, str] = {
    DatabaseTarget.MASTER: "Master router",
    DatabaseTarget.METADATA: "Metadata sidebar",
    DatabaseTarget.LOGS: "Transactional logs",
}

_TARGET_ENV_KEYS: dict[DatabaseTarget, str] = {
    DatabaseTarget.MASTER: "MASTER_ROUTER_DB_URL",
    DatabaseTarget.METADATA: "METADATA_SIDEBAR_DB_URL",
    DatabaseTarget.LOGS: "TRANSACTIONAL_LOGS_DB_URL",
}


class DatabaseConnectionSummary(BaseModel):
    """Sanitized runtime database connection metadata."""

    target: str
    label: str
    env_key: str
    masked_url: str
    source: str = "runtime environment"


class DatabaseConnectionsResponse(BaseModel):
    """Sanitized database connection summary for the admin console."""

    configured: bool
    targets: list[DatabaseConnectionSummary]
    note: str


class CandidateDatabaseConnectionPayload(BaseModel):
    """Write-only replacement URL to test for a single database target."""

    database_url: str = Field(min_length=20, max_length=4_096)


class DatabaseConnectionTestResponse(BaseModel):
    """Sanitized single database test result."""

    target: str
    label: str
    env_key: str
    masked_url: str
    status: Literal["connected", "failed"]
    checked_at: datetime
    error: str | None = None


def _normalize_target(target: str) -> DatabaseTarget:
    try:
        return DatabaseTarget(target)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown database target. Use master, metadata, or logs.",
        ) from exc


def _current_database_url(target: DatabaseTarget) -> str:
    settings = get_settings()
    if target is DatabaseTarget.MASTER:
        return str(settings.master_router_db_url)
    if target is DatabaseTarget.METADATA:
        return str(settings.metadata_sidebar_db_url)
    return str(settings.transactional_logs_db_url)


def _masked_database_url(url: str) -> str:
    parsed = urlsplit(url)
    username = "****" if parsed.username else ""
    password = ":********" if parsed.password else ""
    credentials = f"{username}{password}@" if username or password else ""
    host = parsed.hostname or "unknown-host"
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{credentials}{host}{port}{database}{query}"


def _connection_response(
    target: DatabaseTarget,
    *,
    masked_url: str,
    status_value: Literal["connected", "failed"],
    error: str | None = None,
) -> DatabaseConnectionTestResponse:
    return DatabaseConnectionTestResponse(
        target=target.value,
        label=_TARGET_LABELS[target],
        env_key=_TARGET_ENV_KEYS[target],
        masked_url=masked_url,
        status=status_value,
        checked_at=datetime.now(timezone.utc),
        error=error,
    )


async def _test_candidate_database_url(target: DatabaseTarget, database_url: str) -> DatabaseConnectionTestResponse:
    settings = get_settings()
    engine = create_async_engine(
        sqlalchemy_asyncpg_url(database_url),
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        pool_timeout=settings.network_request_timeout,
    )
    try:
        async with asyncio.timeout(settings.health_check_timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return _connection_response(
            target,
            masked_url=_masked_database_url(database_url),
            status_value="connected",
        )
    except Exception as exc:
        return _connection_response(
            target,
            masked_url=_masked_database_url(database_url),
            status_value="failed",
            error=str(exc),
        )
    finally:
        await engine.dispose()


@database_admin_router.get("/connections", response_model=DatabaseConnectionsResponse)
async def get_database_connections(_: AdminUser) -> DatabaseConnectionsResponse:
    """Return masked current runtime database URLs without exposing credentials."""
    targets = [
        DatabaseConnectionSummary(
            target=target.value,
            label=_TARGET_LABELS[target],
            env_key=_TARGET_ENV_KEYS[target],
            masked_url=_masked_database_url(_current_database_url(target)),
        )
        for target in DatabaseTarget
    ]
    return DatabaseConnectionsResponse(
        configured=True,
        targets=targets,
        note="Only masked runtime URLs are returned. Plain database credentials remain write-only.",
    )


@database_admin_router.post("/connections/{target}/test", response_model=DatabaseConnectionTestResponse)
async def test_current_database_connection(target: str, _: AdminUser) -> DatabaseConnectionTestResponse:
    """Test one current runtime database pool by target."""
    normalized_target = _normalize_target(target)
    masked_url = _masked_database_url(_current_database_url(normalized_target))
    try:
        await get_session_registry().ping(normalized_target)
    except Exception as exc:
        return _connection_response(
            normalized_target,
            masked_url=masked_url,
            status_value="failed",
            error=str(exc),
        )
    return _connection_response(
        normalized_target,
        masked_url=masked_url,
        status_value="connected",
    )


@database_admin_router.post("/connections/{target}/candidate/test", response_model=DatabaseConnectionTestResponse)
async def test_candidate_database_connection(
    target: str,
    payload: CandidateDatabaseConnectionPayload,
    _: AdminUser,
) -> DatabaseConnectionTestResponse:
    """Test one candidate replacement database URL without persisting it."""
    normalized_target = _normalize_target(target)
    result = await _test_candidate_database_url(normalized_target, payload.database_url)
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.model_dump(mode="json"))
    return result
