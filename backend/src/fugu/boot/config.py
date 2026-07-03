"""Validated infrastructure configuration for the Fugu backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Self

from cryptography.fernet import Fernet
from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class InfrastructureConfig(BaseSettings):
    """Parse and validate all infrastructure settings required by Fugu."""

    master_router_db_url: PostgresDsn = Field(validation_alias="MASTER_ROUTER_DB_URL")
    metadata_sidebar_db_url: PostgresDsn = Field(validation_alias="METADATA_SIDEBAR_DB_URL")
    transactional_logs_db_url: PostgresDsn = Field(validation_alias="TRANSACTIONAL_LOGS_DB_URL")

    system_session_secret: SecretStr = Field(validation_alias="SYSTEM_SESSION_SECRET")
    vault_encryption_key: SecretStr = Field(validation_alias="VAULT_ENCRYPTION_KEY")
    jwt_issuer: str = Field("fugu-kernel-core", validation_alias="JWT_ISSUER")
    jwt_audience: str = Field("fugu-studio-client", validation_alias="JWT_AUDIENCE")
    access_token_ttl_minutes: int = Field(
        30,
        ge=5,
        le=1_440,
        validation_alias="ACCESS_TOKEN_TTL_MINUTES",
    )

    db_pool_min_connections: int = Field(2, ge=1, validation_alias="DB_POOL_MIN_CONNECTIONS")
    db_pool_max_connections: int = Field(20, ge=1, validation_alias="DB_POOL_MAX_CONNECTIONS")
    network_request_timeout: float = Field(45.0, gt=0, validation_alias="NETWORK_REQUEST_TIMEOUT")

    allowed_origins: list[AnyHttpUrl] = Field(min_length=1, validation_alias="ALLOWED_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Any) -> Any:
        """Convert a comma-separated environment value into validated HTTP origins."""
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if not origins:
                raise ValueError("ALLOWED_ORIGINS must contain at least one HTTP origin.")
            return origins
        return value

    @field_validator("system_session_secret")
    @classmethod
    def validate_session_secret(cls, value: SecretStr) -> SecretStr:
        """Require sufficient entropy capacity for signing session credentials."""
        if len(value.get_secret_value().strip()) < 32:
            raise ValueError("SYSTEM_SESSION_SECRET must contain at least 32 characters.")
        return value

    @field_validator("vault_encryption_key")
    @classmethod
    def validate_vault_encryption_key(cls, value: SecretStr) -> SecretStr:
        """Require a valid URL-safe Fernet key for encrypted provider credentials."""
        try:
            Fernet(value.get_secret_value().encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("VAULT_ENCRYPTION_KEY must be a valid Fernet key.") from exc
        return value

    @field_validator("jwt_issuer", "jwt_audience")
    @classmethod
    def validate_jwt_scope(cls, value: str) -> str:
        """Reject blank JWT issuer and audience values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("JWT issuer and audience values cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_pool_bounds(self) -> Self:
        """Ensure the maximum connection count is not below the minimum."""
        if self.db_pool_max_connections < self.db_pool_min_connections:
            raise ValueError("DB_POOL_MAX_CONNECTIONS must be greater than or equal to DB_POOL_MIN_CONNECTIONS.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> InfrastructureConfig:
    """Load settings once and raise a startup-safe typed error on invalid configuration."""
    try:
        return InfrastructureConfig()
    except ValidationError as exc:
        raise ConfigurationError(
            "Platform initialization aborted because required configuration is missing or malformed."
        ) from exc
