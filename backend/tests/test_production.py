"""Production CORS, health, lifecycle, and migration orchestration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from fugu.api.routes.health import inspect_database_readiness
from fugu.boot.config import ConfigurationError, InfrastructureConfig, get_settings
from fugu.boot.migrations import MigrationProcessError, run_schema_migrations
from fugu.database.connection import DatabaseTarget
from fugu.main import application_lifespan, create_app


class FakeRuntimeRegistry:
    """In-memory readiness and shutdown probe double."""

    def __init__(self, unavailable: set[DatabaseTarget] | None = None) -> None:
        self.unavailable = unavailable or set()
        self.pinged: list[DatabaseTarget] = []
        self.disposed = False

    async def ping(self, target: DatabaseTarget | str = DatabaseTarget.MASTER) -> None:
        normalized = target if isinstance(target, DatabaseTarget) else DatabaseTarget(target)
        self.pinged.append(normalized)
        if normalized in self.unavailable:
            raise RuntimeError("sensitive database detail")

    async def dispose_pools(self) -> None:
        self.disposed = True


class FakeMigrationConnection:
    """Capture advisory-lock lifecycle without opening PostgreSQL."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False

    async def fetchval(self, query: str, lock_id: int) -> None:
        del lock_id
        if "unlock" in query:
            self.events.append("unlock")
        else:
            self.events.append("lock")

    def is_closed(self) -> bool:
        return self.closed

    async def close(self) -> None:
        self.events.append("close")
        self.closed = True


class FakeMigrationProcess:
    """Capture the Alembic process position in the startup sequence."""

    def __init__(self, events: list[str], return_code: int = 0) -> None:
        self.events = events
        self.return_code = return_code

    async def wait(self) -> int:
        self.events.append("alembic")
        return self.return_code


def build_settings(
    *,
    runtime_environment: str = "test",
    allowed_origins: str = "https://studio.example.com",
    verify_databases_on_startup: bool = True,
) -> InfrastructureConfig:
    """Build a fully validated test runtime configuration."""
    return InfrastructureConfig(
        _env_file=None,
        RUNTIME_ENVIRONMENT=runtime_environment,
        MASTER_ROUTER_DB_URL="postgresql+asyncpg://u:p@localhost:5432/master",
        METADATA_SIDEBAR_DB_URL="postgresql+asyncpg://u:p@localhost:5432/metadata",
        TRANSACTIONAL_LOGS_DB_URL="postgresql+asyncpg://u:p@localhost:5432/logs",
        SYSTEM_SESSION_SECRET="SessionSigningSecretWithAtLeastThirtyTwoCharacters",
        VAULT_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
        ALLOWED_ORIGINS=allowed_origins,
        VERIFY_DATABASES_ON_STARTUP=verify_databases_on_startup,
    )


@pytest.mark.asyncio
async def test_cors_allows_only_configured_exact_origin() -> None:
    settings = build_settings()
    registry = FakeRuntimeRegistry()
    application = create_app(settings=settings, session_registry=registry)  # type: ignore[arg-type]
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        trusted = await client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://studio.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        untrusted = await client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://untrusted.example.net",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert trusted.status_code == 200
    assert trusted.headers["access-control-allow-origin"] == "https://studio.example.com"
    assert trusted.headers.get("access-control-allow-credentials") is None
    assert "access-control-allow-origin" not in untrusted.headers


@pytest.mark.asyncio
async def test_liveness_is_static_and_readiness_checks_all_pools() -> None:
    settings = build_settings()
    registry = FakeRuntimeRegistry()
    application = create_app(settings=settings, session_registry=registry)  # type: ignore[arg-type]
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/api/health/live")
        ready = await client.get("/api/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "connections": {
            "master": "connected",
            "metadata": "connected",
            "logs": "connected",
        },
    }
    assert set(registry.pinged) == set(DatabaseTarget)


@pytest.mark.asyncio
async def test_readiness_returns_sanitized_503_on_dependency_failure() -> None:
    settings = build_settings()
    registry = FakeRuntimeRegistry({DatabaseTarget.LOGS})
    application = create_app(settings=settings, session_registry=registry)  # type: ignore[arg-type]
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["connections"]["logs"] == "unavailable"
    assert "sensitive database detail" not in response.text


@pytest.mark.asyncio
async def test_lifespan_verifies_dependencies_and_disposes_pools() -> None:
    settings = build_settings()
    registry = FakeRuntimeRegistry()
    application = create_app(settings=settings, session_registry=registry)  # type: ignore[arg-type]

    async with application_lifespan(application):
        assert application.state.ready is True

    assert application.state.ready is False
    assert registry.disposed is True


@pytest.mark.asyncio
async def test_lifespan_aborts_startup_when_database_is_unavailable() -> None:
    settings = build_settings()
    registry = FakeRuntimeRegistry({DatabaseTarget.METADATA})
    application = create_app(settings=settings, session_registry=registry)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="startup aborted"):
        async with application_lifespan(application):
            pass

    assert registry.disposed is True


def test_missing_required_configuration_aborts_application_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required_names = (
        "MASTER_ROUTER_DB_URL",
        "METADATA_SIDEBAR_DB_URL",
        "TRANSACTIONAL_LOGS_DB_URL",
        "SYSTEM_SESSION_SECRET",
        "VAULT_ENCRYPTION_KEY",
        "ALLOWED_ORIGINS",
    )
    for name in required_names:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError):
        get_settings()


def test_production_configuration_rejects_insecure_or_wildcard_origins() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        build_settings(
            runtime_environment="production",
            allowed_origins="http://studio.example.com",
        )

    with pytest.raises(ValueError, match="Wildcard"):
        build_settings(allowed_origins="https://*.example.com")


@pytest.mark.asyncio
async def test_readiness_helper_probes_targets_concurrently() -> None:
    registry = FakeRuntimeRegistry({DatabaseTarget.MASTER})
    healthy, connections = await inspect_database_readiness(
        registry,
        timeout_seconds=1.0,
    )

    assert healthy is False
    assert connections["master"] == "unavailable"
    assert set(registry.pinged) == set(DatabaseTarget)


@pytest.mark.asyncio
async def test_migrations_hold_lock_until_alembic_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings()
    events: list[str] = []
    connection = FakeMigrationConnection(events)

    async def fake_connect(**_: Any) -> FakeMigrationConnection:
        return connection

    async def fake_subprocess(*_: Any, **__: Any) -> FakeMigrationProcess:
        return FakeMigrationProcess(events)

    monkeypatch.setattr("fugu.boot.migrations.asyncpg.connect", fake_connect)
    monkeypatch.setattr(
        "fugu.boot.migrations.asyncio.create_subprocess_exec",
        fake_subprocess,
    )

    await run_schema_migrations(settings)

    assert events == ["lock", "alembic", "unlock", "close"]


@pytest.mark.asyncio
async def test_failed_alembic_process_releases_migration_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings()
    events: list[str] = []
    connection = FakeMigrationConnection(events)

    async def fake_connect(**_: Any) -> FakeMigrationConnection:
        return connection

    async def fake_subprocess(*_: Any, **__: Any) -> FakeMigrationProcess:
        return FakeMigrationProcess(events, return_code=2)

    monkeypatch.setattr("fugu.boot.migrations.asyncpg.connect", fake_connect)
    monkeypatch.setattr(
        "fugu.boot.migrations.asyncio.create_subprocess_exec",
        fake_subprocess,
    )

    with pytest.raises(MigrationProcessError):
        await run_schema_migrations(settings)

    assert events == ["lock", "alembic", "unlock", "close"]


def test_entrypoint_runs_migrations_before_uvicorn() -> None:
    entrypoint = Path(__file__).resolve().parents[1] / "entrypoint.sh"
    script = entrypoint.read_text(encoding="utf-8")

    assert script.index("python -m fugu.boot.migrations") < script.index("exec python -m uvicorn")
