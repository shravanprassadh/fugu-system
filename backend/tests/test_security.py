"""Security, authorization, encrypted-vault, and authentication API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fugu.api.dependencies import (
    AdminUser,
    OwnedThread,
    get_identity_security_manager,
)
from fugu.database.connection import (
    DatabaseSessionRegistry,
    DatabaseTarget,
    get_session_registry,
)
from fugu.database.models import Base
from fugu.database.repositories import ThreadRepository, UserRepository
from fugu.main import create_app
from fugu.security.auth import IdentitySecurityManager
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine
from fugu.security.exceptions import (
    DecryptionFailedError,
    InvalidTokenError,
    TokenExpiredError,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TEST_PASSWORD = "UltraSecureStudioAccessKeySignature2026"
TEST_SIGNING_SECRET = "test-signing-secret-with-more-than-thirty-two-characters"


@dataclass
class SecurityIntegrationContext:
    """Resources and identifiers used by authentication integration tests."""

    client: AsyncClient
    registry: DatabaseSessionRegistry
    identity_manager: IdentitySecurityManager
    regular_thread_id: int
    other_thread_id: int


@pytest_asyncio.fixture
async def security_context() -> AsyncIterator[SecurityIntegrationContext]:
    """Create an isolated application with independent in-memory async databases."""
    engines: dict[DatabaseTarget, AsyncEngine] = {
        target: create_async_engine("sqlite+aiosqlite:///:memory:")
        for target in DatabaseTarget
    }
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

    def override_registry() -> DatabaseSessionRegistry:
        return registry

    def override_identity_manager() -> IdentitySecurityManager:
        return identity_manager

    application.dependency_overrides[get_session_registry] = override_registry
    application.dependency_overrides[get_identity_security_manager] = override_identity_manager

    @application.get("/test/admin")
    async def admin_probe(_: AdminUser) -> dict[str, bool]:
        return {"authorized": True}

    @application.get("/test/threads/{thread_id}")
    async def owned_thread_probe(thread: OwnedThread) -> dict[str, int]:
        return {"thread_id": thread.id}

    password_hash = identity_manager.compute_secure_hash(TEST_PASSWORD)
    async with registry.session(DatabaseTarget.MASTER) as session:
        regular_user = await UserRepository.add(
            session,
            username="regular-user",
            password_hash=password_hash,
            role="user",
        )
        admin_user = await UserRepository.add(
            session,
            username="admin-user",
            password_hash=password_hash,
            role="admin",
        )
        other_user = await UserRepository.add(
            session,
            username="other-user",
            password_hash=password_hash,
            role="user",
        )
        regular_thread = await ThreadRepository.add(
            session,
            user_id=regular_user.id,
            name="Regular user's thread",
        )
        other_thread = await ThreadRepository.add(
            session,
            user_id=other_user.id,
            name="Other user's thread",
        )
        _ = admin_user.id
        regular_thread_id = regular_thread.id
        other_thread_id = other_thread.id

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield SecurityIntegrationContext(
            client=client,
            registry=registry,
            identity_manager=identity_manager,
            regular_thread_id=regular_thread_id,
            other_thread_id=other_thread_id,
        )

    application.dependency_overrides.clear()
    await registry.dispose_pools()


async def _login(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


def test_password_hashing_and_verification() -> None:
    """Argon2 hashes must be salted, non-plaintext, and verifiable."""
    password_hash = IdentitySecurityManager.compute_secure_hash(TEST_PASSWORD)

    assert password_hash != TEST_PASSWORD
    assert password_hash.startswith("$argon2")
    assert IdentitySecurityManager.verify_hash_match(TEST_PASSWORD, password_hash)
    assert not IdentitySecurityManager.verify_hash_match("WrongPassword", password_hash)
    assert not IdentitySecurityManager.verify_hash_match(TEST_PASSWORD, "not-a-recognized-hash")


def test_jwt_claims_scope_and_expiration() -> None:
    """Tokens must validate required claims and reject expired or wrong-audience tokens."""
    manager = IdentitySecurityManager(
        signing_secret=TEST_SIGNING_SECRET,
        issuer="issuer-a",
        audience="audience-a",
        access_token_ttl=timedelta(minutes=30),
    )
    token = manager.issue_access_token(
        user_id=12,
        username="token-user",
        role="user",
        token_version=3,
    )
    claims = manager.decode_access_token(token)

    assert claims.user_id == 12
    assert claims.username == "token-user"
    assert claims.role == "user"
    assert claims.ver == 3

    wrong_audience_manager = IdentitySecurityManager(
        signing_secret=TEST_SIGNING_SECRET,
        issuer="issuer-a",
        audience="audience-b",
        access_token_ttl=timedelta(minutes=30),
    )
    with pytest.raises(InvalidTokenError):
        wrong_audience_manager.decode_access_token(token)

    expired_token = manager.issue_access_token(
        user_id=12,
        username="token-user",
        role="user",
        token_version=3,
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        expires_delta=timedelta(minutes=1),
    )
    with pytest.raises(TokenExpiredError):
        manager.decode_access_token(expired_token)


def test_jwt_tampering_is_rejected() -> None:
    """Signature modifications must fail token validation."""
    manager = IdentitySecurityManager(
        signing_secret=TEST_SIGNING_SECRET,
        issuer="issuer-a",
        audience="audience-a",
        access_token_ttl=timedelta(minutes=30),
    )
    token = manager.issue_access_token(
        user_id=1,
        username="token-user",
        role="user",
        token_version=0,
    )

    with pytest.raises(InvalidTokenError):
        manager.decode_access_token(f"{token}tampered")


def test_symmetric_vault_round_trip_and_tamper_rejection() -> None:
    """Provider secrets must encrypt, authenticate, decrypt, and reject corruption."""
    vault = SymmetricVaultEngine(Fernet.generate_key().decode("ascii"))
    plaintext = "sk-provider-sensitive-key"

    encrypted = vault.encrypt_provider_credential(plaintext)
    assert encrypted != plaintext
    assert plaintext not in encrypted
    assert vault.decrypt_provider_credential(encrypted) == plaintext

    tampered = f"{encrypted[:-1]}A"
    with pytest.raises(DecryptionFailedError):
        vault.decrypt_provider_credential(tampered)


@pytest.mark.asyncio
async def test_provider_vault_never_stores_plaintext(
    security_context: SecurityIntegrationContext,
) -> None:
    """Database rows must contain ciphertext while retrieval returns the original value."""
    cipher = SymmetricVaultEngine(Fernet.generate_key().decode("ascii"), key_version=2)
    vault = ProviderCredentialVault(cipher)
    plaintext = "sk-openrouter-sensitive-provider-key"

    async with security_context.registry.session(DatabaseTarget.MASTER) as session:
        credential = await vault.store(
            session,
            provider_name="OpenRouter",
            plaintext_secret=plaintext,
        )
        assert credential.encrypted_secret != plaintext
        assert plaintext not in credential.encrypted_secret
        assert credential.key_version == 2

    async with security_context.registry.session(DatabaseTarget.MASTER) as session:
        assert await vault.retrieve(session, provider_name="openrouter") == plaintext


@pytest.mark.asyncio
async def test_login_profile_logout_and_revocation(
    security_context: SecurityIntegrationContext,
) -> None:
    """Login must issue a usable token and logout must revoke it immediately."""
    login_response = await security_context.client.post(
        "/api/auth/login",
        json={"username": "regular-user", "password": TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    assert login_response.headers["cache-control"] == "no-store"
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile_response = await security_context.client.get("/api/auth/me", headers=headers)
    assert profile_response.status_code == 200
    assert profile_response.json() == {
        "id": 1,
        "username": "regular-user",
        "role": "user",
    }

    logout_response = await security_context.client.post("/api/auth/logout", headers=headers)
    assert logout_response.status_code == 204

    revoked_response = await security_context.client.get("/api/auth/me", headers=headers)
    assert revoked_response.status_code == 401
    assert revoked_response.json()["detail"] == "The access token has been revoked."


@pytest.mark.asyncio
async def test_invalid_login_does_not_disclose_user_existence(
    security_context: SecurityIntegrationContext,
) -> None:
    """Unknown users and wrong passwords must return the same response."""
    unknown_user = await security_context.client.post(
        "/api/auth/login",
        json={"username": "missing-user", "password": TEST_PASSWORD},
    )
    wrong_password = await security_context.client.post(
        "/api/auth/login",
        json={"username": "regular-user", "password": "IncorrectPassword2026"},
    )

    assert unknown_user.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown_user.json() == wrong_password.json()


@pytest.mark.asyncio
async def test_role_and_thread_ownership_authorization(
    security_context: SecurityIntegrationContext,
) -> None:
    """Regular users cannot access admin routes or another user's thread."""
    regular_token = await _login(security_context.client, "regular-user")
    regular_headers = {"Authorization": f"Bearer {regular_token}"}

    own_thread = await security_context.client.get(
        f"/test/threads/{security_context.regular_thread_id}",
        headers=regular_headers,
    )
    other_thread = await security_context.client.get(
        f"/test/threads/{security_context.other_thread_id}",
        headers=regular_headers,
    )
    admin_denied = await security_context.client.get("/test/admin", headers=regular_headers)

    assert own_thread.status_code == 200
    assert other_thread.status_code == 404
    assert admin_denied.status_code == 403

    admin_token = await _login(security_context.client, "admin-user")
    admin_response = await security_context.client.get(
        "/test/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_response.status_code == 200
