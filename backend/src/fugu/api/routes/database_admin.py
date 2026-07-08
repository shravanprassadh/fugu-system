# ruff: noqa: I001
"""Database connection administration routes."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter
from fugu.api.dependencies import AdminUser
from fugu.boot.config import get_settings
from pydantic import BaseModel

database_admin_router = APIRouter(prefix="/api/admin/database", tags=["database-administration"])


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


@database_admin_router.get("/connections", response_model=DatabaseConnectionsResponse)
async def get_database_connections(_: AdminUser) -> DatabaseConnectionsResponse:
    """Return masked current runtime database URLs without exposing credentials."""
    settings = get_settings()
    targets = [
        DatabaseConnectionSummary(
            target="master",
            label="Master router",
            env_key="MASTER_ROUTER_DB_URL",
            masked_url=_masked_database_url(str(settings.master_router_db_url)),
        ),
        DatabaseConnectionSummary(
            target="metadata",
            label="Metadata sidebar",
            env_key="METADATA_SIDEBAR_DB_URL",
            masked_url=_masked_database_url(str(settings.metadata_sidebar_db_url)),
        ),
        DatabaseConnectionSummary(
            target="logs",
            label="Transactional logs",
            env_key="TRANSACTIONAL_LOGS_DB_URL",
            masked_url=_masked_database_url(str(settings.transactional_logs_db_url)),
        ),
    ]
    return DatabaseConnectionsResponse(
        configured=True,
        targets=targets,
        note="Only masked runtime URLs are returned. Plain database credentials remain write-only.",
    )
