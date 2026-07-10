"""Integration tests for atomic provider credential testing and rotation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from fugu.api.dependencies import get_identity_security_manager
from fugu.api.routes import provider_admin
from fugu.boot.config import get_settings
from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.models import Base
from fugu.database.repositories import ProviderCredentialRepository, UserRepository
from fugu.main import create_app
from fugu.providers.credential_validation import CredentialValidationResult
from fugu.security.auth import IdentitySecurityManager
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from tests.database_helpers import create_sqlite_engine_map

TEST_PASSWORD = "ProviderAdminTestPassword2026"
TEST_SIGNING_SECRET = "provider-admin-signing-secret-with-more-than-thirty-two-characters"
VALID_KEY = "provider-key-valid-0001"
REPLACEMENT_KEY = "provider-key-valid-0002"
INVALID_KEY = "provider-key-invalid"


@pytest_asyncio.fixture
async def provider_admin_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, DatabaseSessionRegistry]]:
    """Create an authenticated test application with deterministic provider probes."""
    environment = {
        "MASTER_ROUTER_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db1",
        "METADATA_SIDEBAR_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db2",
        "TRANSACTIONAL_LOGS_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db3",
        "SYSTEM_SESSION_SECRET": TEST_SIGNING_SECRET,
        "VAULT_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "ALLOWED_ORIGINS": "https://myfugu.vercel.app",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()

    async def fake_validate(provider_name: str, secret: str) -> CredentialValidationResult:
        valid = secret != INVALID_KEY
        return CredentialValidationResult(
            provider_name=provider_name,
            valid=valid,
            message=(
                "Credential validation succeeded." if valid else "The provider rejected the candidate credential."
            ),
        )

    monkeypatch.setattr(provider_admin, "validate_provider_credential", fake_validate)

    engines: dict[DatabaseTarget, AsyncEngine] = create_sqlite_engine_map()
    registry = DatabaseSessionRegistry(engines)
    for engine in engines.values():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    identity_manager = IdentitySecurityManager(
        signing_secret=TEST_SIGNING_SECRET,
        issuer="test-fugu-issuer",
        audience="test-fugu-client",
        access_token_ttl=timedelta(minutes=30),
    )
    application = create_app()
    application.dependency_overrides[get_session_registry] = lambda: registry
    application.dependency_overrides[get_identity_security_manager] = lambda: identity_manager

    async with registry.session(DatabaseTarget.MASTER) as session:
        await UserRepository.add(
            session,
            username="admin-user",
            password_hash=identity_manager.compute_secure_hash(TEST_PASSWORD),
            role="admin",
        )

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, registry

    application.dependency_overrides.clear()
    await registry.dispose_pools()
    get_settings.cache_clear()


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin-user", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_failed_candidate_preserves_active_ciphertext_and_version(
    provider_admin_client: tuple[AsyncClient, DatabaseSessionRegistry],
) -> None:
    """A rejected candidate records failure metadata without replacing the active key."""
    client, registry = provider_admin_client
    headers = await _admin_headers(client)

    created = await client.post(
        "/api/admin/provider-credentials",
        headers=headers,
        json={"provider_name": "openrouter", "secret": VALID_KEY},
    )
    assert created.status_code == 200
    assert created.json()["activated"] is True
    assert created.json()["credential"]["key_version"] == 1

    async with registry.session(DatabaseTarget.MASTER) as session:
        before = await ProviderCredentialRepository.get_by_provider(session, "openrouter")
        assert before is not None
        ciphertext_before = before.encrypted_secret
        version_before = before.key_version

    rejected = await client.put(
        "/api/admin/provider-credentials/openrouter",
        headers=headers,
        json={"secret": INVALID_KEY},
    )
    assert rejected.status_code == 200
    payload = rejected.json()
    assert payload["activated"] is False
    assert payload["credential"]["key_version"] == version_before
    assert payload["credential"]["last_test_failure_at"] is not None
    assert "rejected" in payload["credential"]["last_test_failure_message"]

    async with registry.session(DatabaseTarget.MASTER) as session:
        after = await ProviderCredentialRepository.get_by_provider(session, "openrouter")
        assert after is not None
        assert after.encrypted_secret == ciphertext_before
        assert after.key_version == version_before
        vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
        assert await vault.retrieve(session, provider_name="openrouter") == VALID_KEY


@pytest.mark.asyncio
async def test_successful_candidate_replaces_key_and_advances_version(
    provider_admin_client: tuple[AsyncClient, DatabaseSessionRegistry],
) -> None:
    """A validated candidate atomically replaces the key and advances its revision."""
    client, registry = provider_admin_client
    headers = await _admin_headers(client)

    created = await client.post(
        "/api/admin/provider-credentials",
        headers=headers,
        json={"provider_name": "nvidia", "secret": VALID_KEY},
    )
    assert created.status_code == 200

    candidate_test = await client.post(
        "/api/admin/provider-credentials/nvidia/candidate/test",
        headers=headers,
        json={"secret": REPLACEMENT_KEY},
    )
    assert candidate_test.status_code == 200
    assert candidate_test.json()["valid"] is True

    replaced = await client.put(
        "/api/admin/provider-credentials/nvidia",
        headers=headers,
        json={"secret": REPLACEMENT_KEY},
    )
    assert replaced.status_code == 200
    payload = replaced.json()
    assert payload["activated"] is True
    assert payload["credential"]["key_version"] == 2
    assert payload["credential"]["last_successful_test_at"] is not None

    active_test = await client.post(
        "/api/admin/provider-credentials/nvidia/test",
        headers=headers,
    )
    assert active_test.status_code == 200
    assert active_test.json()["valid"] is True

    async with registry.session(DatabaseTarget.MASTER) as session:
        vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
        assert await vault.retrieve(session, provider_name="nvidia") == REPLACEMENT_KEY


@pytest.mark.asyncio
async def test_candidate_test_does_not_create_provider_record(
    provider_admin_client: tuple[AsyncClient, DatabaseSessionRegistry],
) -> None:
    """Testing a candidate alone must never activate or persist it."""
    client, registry = provider_admin_client
    headers = await _admin_headers(client)

    response = await client.post(
        "/api/admin/provider-credentials/openrouter/candidate/test",
        headers=headers,
        json={"secret": VALID_KEY},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True

    async with registry.session(DatabaseTarget.MASTER) as session:
        assert await ProviderCredentialRepository.get_by_provider(session, "openrouter") is None
