"""Tests for execution diagnostic redaction and the admin run inspector."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.api.dependencies import get_identity_security_manager
from fugu.boot.config import get_settings
from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.models import Base, PipelineRun, PipelineStepRun
from fugu.database.repositories import (
    PipelineVersionRepository,
    ThreadRepository,
    UserRepository,
)
from fugu.execution.diagnostics import (
    classify_execution_error,
    sanitise_diagnostic_text,
)
from fugu.main import create_app
from fugu.security.auth import IdentitySecurityManager
from tests.database_helpers import create_sqlite_engine_map

ADMIN_PASSWORD = "ExecutionAdminPassword2026"
USER_PASSWORD = "ExecutionUserPassword2026"
SIGNING_SECRET = "execution-diagnostics-signing-secret-with-more-than-thirty-two-characters"


def test_sanitiser_redacts_credentials_stack_traces_and_limits_content() -> None:
    diagnostic = (
        "authorization: Bearer super-secret-token\n"
        "api_key=sk-abcdefghijklmnopqrstuvwxyz123456\n"
        "Traceback (most recent call last):\n"
        '  File "/srv/fugu/providers.py", line 42, in stream\n'
        "provider request failed"
    )

    sanitised = sanitise_diagnostic_text(diagnostic)

    assert sanitised is not None
    assert "super-secret-token" not in sanitised
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in sanitised
    assert "Traceback" not in sanitised
    assert 'File "/srv/fugu/providers.py"' not in sanitised
    assert "provider request failed" in sanitised


def test_actionable_error_identifies_stage_without_echoing_provider_payload() -> None:
    safe = classify_execution_error(
        ValueError("The thinking budget 256 is invalid. api_key=sk-abcdefghijklmnopqrstuvwxyz123456"),
        stage_name="verifier",
    )

    assert safe.category == "invalid_model_parameter"
    assert safe.retryable is False
    assert "verifier" in safe.message
    assert "256" not in safe.message
    assert "sk-" not in safe.message


@pytest_asyncio.fixture
async def execution_admin_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, DatabaseSessionRegistry, int]]:
    environment = {
        "MASTER_ROUTER_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db1",
        "METADATA_SIDEBAR_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db2",
        "TRANSACTIONAL_LOGS_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db3",
        "SYSTEM_SESSION_SECRET": SIGNING_SECRET,
        "VAULT_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "ALLOWED_ORIGINS": "https://myfugu.vercel.app",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()

    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    identity_manager = IdentitySecurityManager(
        signing_secret=SIGNING_SECRET,
        issuer="execution-test-issuer",
        audience="execution-test-client",
        access_token_ttl=timedelta(minutes=30),
    )
    application = create_app()
    application.dependency_overrides[get_session_registry] = lambda: registry
    application.dependency_overrides[get_identity_security_manager] = lambda: identity_manager

    async with registry.session(DatabaseTarget.MASTER) as session:
        admin = await UserRepository.add(
            session,
            username="execution-admin",
            password_hash=identity_manager.compute_secure_hash(ADMIN_PASSWORD),
            role="admin",
        )
        user = await UserRepository.add(
            session,
            username="execution-user",
            password_hash=identity_manager.compute_secure_hash(USER_PASSWORD),
            role="user",
        )
        thread = await ThreadRepository.add(session, user_id=user.id, name="Failed verification run")
        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=admin.id,
            change_description="Inspectable pipeline",
            state="published",
        )
        version.validation_status = "valid"
        version.validated_at = datetime.now(timezone.utc)
        version.published_at = datetime.now(timezone.utc)
        await PipelineVersionRepository.add_stage(
            session,
            pipeline_version_id=version.id,
            stable_identifier="reader",
            name="Reader",
            description="Reads the request.",
            enabled=True,
            position=1,
            provider_type="openrouter",
            model_string="openrouter/free",
            system_prompt_directives="Read the request.",
            prerequisite_dependencies=[],
            is_terminal=False,
            required_capabilities=["text_generation"],
        )
        await PipelineVersionRepository.add_stage(
            session,
            pipeline_version_id=version.id,
            stable_identifier="verifier",
            name="Verifier",
            description="Checks the response.",
            enabled=True,
            position=2,
            provider_type="openrouter",
            model_string="openrouter/free",
            system_prompt_directives="Verify the response.",
            prerequisite_dependencies=["reader"],
            is_terminal=True,
            thinking_budget=512,
            retry_count=1,
            required_capabilities=["text_generation"],
        )
        run = PipelineRun(
            thread_id=thread.id,
            pipeline_version_id=version.id,
            status="failed",
            error_code="ValueError",
            error_message="The thinking budget 256 is invalid. credential=private-provider-key",
            completed_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                PipelineStepRun(
                    run_id=run.id,
                    step_name="reader",
                    status="completed",
                    output_trace="Request understood. authorization: Bearer hidden-token",
                    completed_at=datetime.now(timezone.utc),
                ),
                PipelineStepRun(
                    run_id=run.id,
                    step_name="verifier",
                    status="failed",
                    output_trace=(
                        "Partial verification. api_key=sk-abcdefghijklmnopqrstuvwxyz123456\n"
                        "Traceback (most recent call last):\n"
                        '  File "/srv/fugu/provider.py", line 9, in call'
                    ),
                    error_message="The thinking budget 256 is invalid.",
                    completed_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.flush()
        run_id = run.id

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, registry, run_id

    application.dependency_overrides.clear()
    await registry.dispose_pools()
    get_settings.cache_clear()


async def _headers(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_can_filter_inspect_and_export_sanitised_run_diagnostics(
    execution_admin_client: tuple[AsyncClient, DatabaseSessionRegistry, int],
) -> None:
    client, _, run_id = execution_admin_client
    headers = await _headers(client, "execution-admin", ADMIN_PASSWORD)

    history = await client.get(
        "/api/admin/execution-runs",
        headers=headers,
        params={
            "status": "failed",
            "provider": "openrouter",
            "model": "openrouter/free",
        },
    )
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [run_id]
    assert history.json()[0]["failed_stage"] == "verifier"
    assert history.json()[0]["error_category"] == "invalid_model_parameter"

    detail = await client.get(f"/api/admin/execution-runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["pipeline_version_number"] == 1
    assert [stage["step_name"] for stage in payload["stages"]] == ["reader", "verifier"]
    verifier = payload["stages"][1]
    assert verifier["provider"] == "openrouter"
    assert verifier["configured_retry_count"] == 1
    assert verifier["error_category"] == "invalid_model_parameter"
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in verifier["sanitised_output"]
    assert "Traceback" not in verifier["sanitised_output"]
    assert 'File "/srv/fugu/provider.py"' not in verifier["sanitised_output"]

    exported = await client.get(f"/api/admin/execution-runs/{run_id}/diagnostics", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["run"]["id"] == run_id
    assert "hidden-token" not in str(exported.json())
    assert "private-provider-key" not in str(exported.json())


@pytest.mark.asyncio
async def test_standard_user_cannot_access_internal_stage_diagnostics(
    execution_admin_client: tuple[AsyncClient, DatabaseSessionRegistry, int],
) -> None:
    client, _, run_id = execution_admin_client
    headers = await _headers(client, "execution-user", USER_PASSWORD)

    history = await client.get("/api/admin/execution-runs", headers=headers)
    detail = await client.get(f"/api/admin/execution-runs/{run_id}", headers=headers)

    assert history.status_code == 403
    assert detail.status_code == 403
