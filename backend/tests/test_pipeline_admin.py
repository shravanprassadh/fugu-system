"""Integration tests for the versioned pipeline administration API."""

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
from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget, get_session_registry
from fugu.database.models import Base, PipelineVersion, ProviderCredential
from fugu.database.repositories import PipelineVersionRepository, UserRepository
from fugu.main import create_app
from fugu.security.auth import IdentitySecurityManager
from tests.database_helpers import create_sqlite_engine_map

ADMIN_PASSWORD = "PipelineAdminPassword2026"
USER_PASSWORD = "PipelineUserPassword2026"
SIGNING_SECRET = "pipeline-admin-signing-secret-with-more-than-thirty-two-characters"


@pytest_asyncio.fixture
async def pipeline_admin_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, DatabaseSessionRegistry]]:
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
        issuer="pipeline-test-issuer",
        audience="pipeline-test-client",
        access_token_ttl=timedelta(minutes=30),
    )
    application = create_app()
    application.dependency_overrides[get_session_registry] = lambda: registry
    application.dependency_overrides[get_identity_security_manager] = lambda: identity_manager

    async with registry.session(DatabaseTarget.MASTER) as session:
        admin = await UserRepository.add(
            session,
            username="pipeline-admin",
            password_hash=identity_manager.compute_secure_hash(ADMIN_PASSWORD),
            role="admin",
        )
        await UserRepository.add(
            session,
            username="pipeline-user",
            password_hash=identity_manager.compute_secure_hash(USER_PASSWORD),
            role="user",
        )
        session.add(
            ProviderCredential(
                provider_name="openrouter",
                encrypted_secret="encrypted-provider-test-value",
                key_version=1,
            )
        )
        version = await PipelineVersionRepository.create(
            session,
            created_by_user_id=admin.id,
            change_description="Initial published pipeline",
            state="published",
        )
        version.validation_status = "valid"
        version.validation_issues = []
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
            stable_identifier="consolidator",
            name="Consolidator",
            description="Returns the answer.",
            enabled=True,
            position=2,
            provider_type="openrouter",
            model_string="openrouter/free",
            system_prompt_directives="Return the final answer.",
            prerequisite_dependencies=["reader"],
            is_terminal=True,
            temperature=0.7,
            token_limit=1024,
            required_capabilities=["text_generation"],
        )

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, registry

    application.dependency_overrides.clear()
    await registry.dispose_pools()
    get_settings.cache_clear()


async def _headers(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _stage(
    identifier: str,
    position: int,
    *,
    prerequisites: list[str] | None = None,
    terminal: bool = False,
    name: str | None = None,
) -> dict[str, object]:
    return {
        "stable_identifier": identifier,
        "name": name or identifier.title(),
        "description": f"{identifier} stage",
        "enabled": True,
        "position": position,
        "provider_type": "openrouter",
        "model_string": "openrouter/free",
        "system_prompt_directives": f"Execute {identifier}.",
        "prerequisite_dependencies": prerequisites or [],
        "is_terminal": terminal,
        "temperature": 0.7,
        "thinking_budget": None,
        "token_limit": 1024,
        "timeout_seconds": 45,
        "retry_count": 0,
        "fallback_provider_type": None,
        "fallback_model_string": None,
        "input_policy": {},
        "output_policy": {},
        "required_capabilities": ["text_generation"],
    }


@pytest.mark.asyncio
async def test_admin_can_create_save_validate_publish_and_rollback(
    pipeline_admin_client: tuple[AsyncClient, DatabaseSessionRegistry],
) -> None:
    client, registry = pipeline_admin_client
    headers = await _headers(client, "pipeline-admin", ADMIN_PASSWORD)

    initial = await client.get("/api/admin/pipeline-versions", headers=headers)
    assert initial.status_code == 200
    assert initial.json()[0]["state"] == "published"
    original_id = initial.json()[0]["id"]

    created = await client.post(
        "/api/admin/pipeline-versions/drafts",
        headers=headers,
        json={"change_description": "Add a verifier stage"},
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["state"] == "draft"
    assert draft["stage_count"] == 2

    saved = await client.put(
        f"/api/admin/pipeline-versions/{draft['id']}",
        headers=headers,
        json={
            "change_description": "Add a verifier stage",
            "stages": [
                _stage("reader", 1),
                _stage("verifier", 2, prerequisites=["reader"]),
                _stage("consolidator", 3, prerequisites=["reader", "verifier"], terminal=True),
            ],
        },
    )
    assert saved.status_code == 200
    assert [stage["stable_identifier"] for stage in saved.json()["stages"]] == [
        "reader",
        "verifier",
        "consolidator",
    ]
    assert saved.json()["validation_status"] == "pending"

    validated = await client.post(
        f"/api/admin/pipeline-versions/{draft['id']}/validate",
        headers=headers,
    )
    assert validated.status_code == 200
    assert validated.json()["valid"] is True

    published = await client.post(
        f"/api/admin/pipeline-versions/{draft['id']}/publish",
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["published"] is True
    assert published.json()["version"]["state"] == "published"

    immutable = await client.put(
        f"/api/admin/pipeline-versions/{draft['id']}",
        headers=headers,
        json={"change_description": "Illegal rewrite", "stages": [_stage("only", 1, terminal=True)]},
    )
    assert immutable.status_code == 409

    rollback = await client.post(
        f"/api/admin/pipeline-versions/{original_id}/rollback",
        headers=headers,
        json={"change_description": "Restore the original two-stage pipeline"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["published"] is True
    rolled_back = rollback.json()["version"]
    assert rolled_back["version_number"] > published.json()["version"]["version_number"]
    assert [stage["stable_identifier"] for stage in rolled_back["stages"]] == ["reader", "consolidator"]

    async with registry.session(DatabaseTarget.MASTER) as session:
        current = await PipelineVersionRepository.require_current_published(session)
        versions = await PipelineVersionRepository.list_versions(session)
        assert current.id == rolled_back["id"]
        assert sum(version.state == "published" for version in versions) == 1


@pytest.mark.asyncio
async def test_invalid_publication_persists_issues_without_replacing_active_version(
    pipeline_admin_client: tuple[AsyncClient, DatabaseSessionRegistry],
) -> None:
    client, registry = pipeline_admin_client
    headers = await _headers(client, "pipeline-admin", ADMIN_PASSWORD)
    async with registry.session(DatabaseTarget.MASTER) as session:
        active_before = await PipelineVersionRepository.require_current_published(session)
        active_before_id = active_before.id

    created = await client.post(
        "/api/admin/pipeline-versions/drafts",
        headers=headers,
        json={"change_description": "Broken cyclic draft"},
    )
    draft_id = created.json()["id"]
    saved = await client.put(
        f"/api/admin/pipeline-versions/{draft_id}",
        headers=headers,
        json={
            "change_description": "Broken cyclic draft",
            "stages": [
                _stage("reader", 1, prerequisites=["consolidator"]),
                _stage("consolidator", 2, prerequisites=["reader"], terminal=True),
            ],
        },
    )
    assert saved.status_code == 200

    rejected = await client.post(
        f"/api/admin/pipeline-versions/{draft_id}/publish",
        headers=headers,
    )
    assert rejected.status_code == 422
    assert rejected.json()["published"] is False
    assert "dependency_cycle" in {issue["code"] for issue in rejected.json()["issues"]}

    stored = await client.get(f"/api/admin/pipeline-versions/{draft_id}", headers=headers)
    assert stored.status_code == 200
    assert stored.json()["state"] == "draft"
    assert stored.json()["validation_status"] == "invalid"

    async with registry.session(DatabaseTarget.MASTER) as session:
        active_after = await PipelineVersionRepository.require_current_published(session)
        assert active_after.id == active_before_id


@pytest.mark.asyncio
async def test_non_admin_is_forbidden_and_only_drafts_can_be_deleted(
    pipeline_admin_client: tuple[AsyncClient, DatabaseSessionRegistry],
) -> None:
    client, _ = pipeline_admin_client
    user_headers = await _headers(client, "pipeline-user", USER_PASSWORD)
    forbidden = await client.get("/api/admin/pipeline-versions", headers=user_headers)
    assert forbidden.status_code == 403

    admin_headers = await _headers(client, "pipeline-admin", ADMIN_PASSWORD)
    versions = await client.get("/api/admin/pipeline-versions", headers=admin_headers)
    published_id = versions.json()[0]["id"]
    rejected = await client.delete(f"/api/admin/pipeline-versions/{published_id}", headers=admin_headers)
    assert rejected.status_code == 409

    draft = await client.post(
        "/api/admin/pipeline-versions/drafts",
        headers=admin_headers,
        json={"change_description": "Temporary draft"},
    )
    deleted = await client.delete(
        f"/api/admin/pipeline-versions/{draft.json()['id']}",
        headers=admin_headers,
    )
    assert deleted.status_code == 204
    missing = await client.get(
        f"/api/admin/pipeline-versions/{draft.json()['id']}",
        headers=admin_headers,
    )
    assert missing.status_code == 404
