"""Tests for strict infrastructure configuration validation."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from pydantic import ValidationError

from fugu.boot.config import ConfigurationError, InfrastructureConfig, get_settings

REQUIRED_ENVIRONMENT_VARIABLES = (
    "MASTER_ROUTER_DB_URL",
    "METADATA_SIDEBAR_DB_URL",
    "TRANSACTIONAL_LOGS_DB_URL",
    "SYSTEM_SESSION_SECRET",
    "VAULT_ENCRYPTION_KEY",
    "JWT_ISSUER",
    "JWT_AUDIENCE",
    "ACCESS_TOKEN_TTL_MINUTES",
    "DB_POOL_MIN_CONNECTIONS",
    "DB_POOL_MAX_CONNECTIONS",
    "NETWORK_REQUEST_TIMEOUT",
    "ALLOWED_ORIGINS",
)

VALID_CONTEXT = {
    "MASTER_ROUTER_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db1",
    "METADATA_SIDEBAR_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db2",
    "TRANSACTIONAL_LOGS_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db3",
    "SYSTEM_SESSION_SECRET": "SessionSigningSecretWithAtLeastThirtyTwoCharacters",
    "VAULT_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "ALLOWED_ORIGINS": "http://localhost:3000,https://studio.example.com",
}


@pytest.fixture(autouse=True)
def clear_configuration_environment(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Prevent developer or CI environment variables from masking missing-value tests."""
    for variable_name in REQUIRED_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_config_ingestion_success() -> None:
    """Parse valid environment-style aliases and apply resource defaults."""
    config = InfrastructureConfig(_env_file=None, **VALID_CONTEXT)

    assert config.db_pool_min_connections == 2
    assert config.db_pool_max_connections == 20
    assert config.network_request_timeout == 45.0
    assert config.jwt_issuer == "fugu-kernel-core"
    assert config.jwt_audience == "fugu-studio-client"
    assert config.access_token_ttl_minutes == 30
    assert "db1" in str(config.master_router_db_url)
    assert [str(origin).rstrip("/") for origin in config.allowed_origins] == [
        "http://localhost:3000",
        "https://studio.example.com",
    ]


def test_config_ingestion_fails_on_missing_parameters() -> None:
    """Reject configuration when mandatory values are absent."""
    incomplete_context = {
        "MASTER_ROUTER_DB_URL": VALID_CONTEXT["MASTER_ROUTER_DB_URL"],
        "SYSTEM_SESSION_SECRET": VALID_CONTEXT["SYSTEM_SESSION_SECRET"],
    }

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **incomplete_context)


def test_config_ingestion_fails_on_short_session_secret() -> None:
    """Reject signing secrets without enough entropy capacity."""
    malformed_context = {**VALID_CONTEXT, "SYSTEM_SESSION_SECRET": "too-short"}

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **malformed_context)


def test_config_ingestion_rejects_invalid_fernet_key() -> None:
    """Reject encryption keys that cannot initialize Fernet."""
    malformed_context = {**VALID_CONTEXT, "VAULT_ENCRYPTION_KEY": "not-a-valid-fernet-key"}

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **malformed_context)


def test_config_ingestion_rejects_blank_jwt_scope() -> None:
    """Reject blank JWT issuer or audience values."""
    malformed_context = {**VALID_CONTEXT, "JWT_AUDIENCE": " "}

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **malformed_context)


def test_config_ingestion_rejects_invalid_token_ttl() -> None:
    """Reject access-token lifetimes outside the permitted range."""
    malformed_context = {**VALID_CONTEXT, "ACCESS_TOKEN_TTL_MINUTES": 2}

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **malformed_context)


def test_config_ingestion_rejects_inverted_pool_bounds() -> None:
    """Reject connection-pool limits where the maximum is below the minimum."""
    malformed_context = {
        **VALID_CONTEXT,
        "DB_POOL_MIN_CONNECTIONS": 10,
        "DB_POOL_MAX_CONNECTIONS": 5,
    }

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **malformed_context)


def test_get_settings_raises_typed_configuration_error() -> None:
    """Translate Pydantic validation failures into the backend startup exception."""
    with pytest.raises(ConfigurationError):
        get_settings()
