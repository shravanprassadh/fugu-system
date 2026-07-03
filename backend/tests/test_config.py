"""Tests for strict infrastructure configuration validation."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from pydantic import ValidationError

from fugu.boot.config import InfrastructureConfig

REQUIRED_ENVIRONMENT_VARIABLES = (
    "MASTER_ROUTER_DB_URL",
    "METADATA_SIDEBAR_DB_URL",
    "TRANSACTIONAL_LOGS_DB_URL",
    "ADMIN_ACCESS_PASSPHRASE",
    "SYSTEM_SESSION_SECRET",
    "VAULT_ENCRYPTION_KEY",
    "DB_POOL_MIN_CONNECTIONS",
    "DB_POOL_MAX_CONNECTIONS",
    "NETWORK_REQUEST_TIMEOUT",
    "ALLOWED_ORIGINS",
)

VALID_CONTEXT = {
    "MASTER_ROUTER_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db1",
    "METADATA_SIDEBAR_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db2",
    "TRANSACTIONAL_LOGS_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db3",
    "ADMIN_ACCESS_PASSPHRASE": "HighEntropyAdministrativePassphrase",
    "SYSTEM_SESSION_SECRET": "SessionSigningSecretWithAtLeastThirtyTwoCharacters",
    "VAULT_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "ALLOWED_ORIGINS": "http://localhost:3000,https://studio.example.com",
}


@pytest.fixture(autouse=True)
def clear_configuration_environment(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Prevent developer or CI environment variables from masking missing-value tests."""
    for variable_name in REQUIRED_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)
    yield


def test_config_ingestion_success() -> None:
    """Parse valid environment-style aliases and apply resource defaults."""
    config = InfrastructureConfig(_env_file=None, **VALID_CONTEXT)

    assert config.db_pool_min_connections == 2
    assert config.db_pool_max_connections == 20
    assert config.network_request_timeout == 45.0
    assert "db1" in str(config.master_router_db_url)
    assert [str(origin).rstrip("/") for origin in config.allowed_origins] == [
        "http://localhost:3000",
        "https://studio.example.com",
    ]


def test_config_ingestion_fails_on_missing_parameters() -> None:
    """Reject configuration when mandatory values are absent."""
    incomplete_context = {
        "MASTER_ROUTER_DB_URL": VALID_CONTEXT["MASTER_ROUTER_DB_URL"],
        "ADMIN_ACCESS_PASSPHRASE": VALID_CONTEXT["ADMIN_ACCESS_PASSPHRASE"],
    }

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **incomplete_context)


def test_config_ingestion_fails_on_blank_strings() -> None:
    """Reject whitespace-only required values."""
    malformed_context = {**VALID_CONTEXT, "ADMIN_ACCESS_PASSPHRASE": " "}

    with pytest.raises(ValidationError):
        InfrastructureConfig(_env_file=None, **malformed_context)


def test_config_ingestion_rejects_invalid_fernet_key() -> None:
    """Reject encryption keys that cannot initialize Fernet."""
    malformed_context = {**VALID_CONTEXT, "VAULT_ENCRYPTION_KEY": "not-a-valid-fernet-key"}

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
