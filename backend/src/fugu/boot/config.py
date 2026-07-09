"""Validated infrastructure configuration for the Fugu backend."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

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
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

from fugu.database.urls import sqlalchemy_asyncpg_url


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class InfrastructureConfig(BaseSettings):
    """Parse and validate all infrastructure settings required by Fugu."""

    runtime_environment: Literal["development", "test", "staging", "production"] = Field(
        "development",
        validation_alias="RUNTIME_ENVIRONMENT",
    )

    master_router_db_url: PostgresDsn = Field(validation_alias="MASTER_ROUTER_DB_URL")
    metadata_sidebar_db_url: PostgresDsn = Field(validation_alias="METADATA_SIDEBAR_DB_URL")
    transactional_logs_db_url: PostgresDsn = Field(validation_alias="TRANSACTIONAL_LOGS_DB_URL")

    system_session_secret: SecretStr = Field(validation_alias="SYSTEM_SESSION_SECRET")
    vault_encryption_key: SecretStr = Field(validation_alias="VAULT_ENCRYPTION_KEY")
    jwt_issuer: str = Field("fugu-kernel-core", validation_alias="JWT_ISSUER")
    jwt_audience: str = Field("fugu-studio-client", validation_alias="JWT_AUDIENCE")
    access_token_ttl_minutes: int = Field(
        2_880,
        ge=5,
        le=10_080,
        validation_alias="ACCESS_TOKEN_TTL_MINUTES",
    )

    db_pool_min_connections: int = Field(
        2,
        ge=1,
        validation_alias="DB_POOL_MIN_CONNECTIONS",
    )
    db_pool_max_connections: int = Field(
        20,
        ge=1,
        validation_alias="DB_POOL_MAX_CONNECTIONS",
    )
    network_request_timeout: float = Field(
        45.0,
        gt=0,
        validation_alias="NETWORK_REQUEST_TIMEOUT",
    )
    health_check_timeout_seconds: float = Field(
        3.0,
        gt=0,
        le=30.0,
        validation_alias="HEALTH_CHECK_TIMEOUT_SECONDS",
    )
    verify_databases_on_startup: bool = Field(
        True,
        validation_alias="VERIFY_DATABASES_ON_STARTUP",
    )

    migration_lock_id: int = Field(
        726_846_354_297,
        ge=1,
        le=9_223_372_036_854_775_807,
        validation_alias="MIGRATION_LOCK_ID",
    )
    migration_lock_timeout_seconds: float = Field(
        120.0,
        gt=0,
        le=1_800.0,
        validation_alias="MIGRATION_LOCK_TIMEOUT_SECONDS",
    )

    cors_preflight_max_age_seconds: int = Field(
        600,
        ge=0,
        le=86_400,
        validation_alias="CORS_PREFLIGHT_MAX_AGE_SECONDS",
    )
    allowed_origins: Annotated[list[AnyHttpUrl], NoDecode] = Field(
        min_length=1,
        validation_alias="ALLOWED_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    @field_validator(
        "master_router_db_url",
        "metadata_sidebar_db_url",
        "transactional_logs_db_url",
        mode="before",
    )
    @classmethod
    def normalize_database_url(cls, value: Any) -> Any:
        """Canonicalize PostgreSQL schemes, async driver, and SSL options once."""
        if isinstance(value, str):
            return sqlalchemy_asyncpg_url(value)
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Any) -> Any:
        """Convert JSON-list or comma-separated environment values into HTTP origins."""
        if isinstance(value, str):
            normalized_value = value.strip()
            if not normalized_value:
                raise ValueError("ALLOWED_ORIGINS must contain at least one HTTP origin.")
            if normalized_value.startswith("["):
                try:
                    decoded_value = json.loads(normalized_value)
                except json.JSONDecodeError as exc:
                    raise ValueError("ALLOWED_ORIGINS JSON list is malformed.") from exc
                if not isinstance(decoded_value, list):
                    raise ValueError("ALLOWED_ORIGINS JSON value must be a list of HTTP origins.")
                origins = [str(origin).strip() for origin in decoded_value if str(origin).strip()]
            else:
                origins = [origin.strip() for origin in normalized_value.split(",") if origin.strip()]
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
    def validate_runtime_boundaries(self) -> Self:
        """Validate pool limits and exact origin-only CORS boundaries."""
        if self.db_pool_max_connections < self.db_pool_min_connections:
            raise ValueError("DB_POOL_MAX_CONNECTIONS must be greater than or equal to DB_POOL_MIN_CONNECTIONS.")

        normalized_origins: set[str] = set()
        for origin in self.allowed_origins:
            origin_text = str(origin).rstrip("/")
            parsed = urlsplit(origin_text)
            if "*" in origin_text:
                raise ValueError("Wildcard CORS origins are prohibited.")
            if parsed.username or parsed.password:
                raise ValueError("CORS origins cannot contain user information.")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("CORS entries must be origins without paths, queries, or fragments.")
            if origin_text in normalized_origins:
                raise ValueError("ALLOWED_ORIGINS cannot contain duplicate origins.")
            normalized_origins.add(origin_text)

            if self.runtime_environment == "production":
                if parsed.scheme != "https":
                    raise ValueError("Production CORS origins must use HTTPS.")
                if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                    raise ValueError("Production CORS origins cannot reference loopback hosts.")

        return self

    @property
    def cors_origins(self) -> tuple[str, ...]:
        """Return normalized exact origins suitable for Starlette CORSMiddleware."""
        return tuple(str(origin).rstrip("/") for origin in self.allowed_origins)


@lru_cache(maxsize=1)
def get_settings() -> InfrastructureConfig:
    """Load settings once and raise a startup-safe typed error on invalid configuration."""
    try:
        return InfrastructureConfig()
    except (SettingsError, ValidationError) as exc:
        raise ConfigurationError(
            "Platform initialization aborted because required configuration is missing or malformed."
        ) from exc
