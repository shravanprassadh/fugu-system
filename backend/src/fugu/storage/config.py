"""Lazy attachment-storage configuration independent of core application startup."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AttachmentStorageConfig(BaseSettings):
    """Validate object-storage and upload limits only when attachments are used."""

    backend: Literal["disabled", "local", "s3-compatible"] = Field(
        "disabled",
        validation_alias="ATTACHMENT_STORAGE_BACKEND",
    )
    bucket: str = Field("fugu-attachments", min_length=1, max_length=255, validation_alias="ATTACHMENT_STORAGE_BUCKET")
    local_root: Path = Field(Path(".fugu/attachments"), validation_alias="ATTACHMENT_STORAGE_LOCAL_ROOT")
    s3_endpoint_url: str | None = Field(None, validation_alias="ATTACHMENT_STORAGE_S3_ENDPOINT_URL")
    s3_region: str = Field("auto", min_length=1, max_length=100, validation_alias="ATTACHMENT_STORAGE_S3_REGION")
    s3_access_key_id: SecretStr | None = Field(None, validation_alias="ATTACHMENT_STORAGE_S3_ACCESS_KEY_ID")
    s3_secret_access_key: SecretStr | None = Field(None, validation_alias="ATTACHMENT_STORAGE_S3_SECRET_ACCESS_KEY")
    max_file_size_bytes: int = Field(
        25 * 1024 * 1024,
        ge=1,
        le=100 * 1024 * 1024,
        validation_alias="ATTACHMENT_MAX_FILE_SIZE_BYTES",
    )

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    @model_validator(mode="after")
    def validate_backend(self) -> Self:
        """Require complete S3-compatible credentials and a non-empty local root."""
        if self.backend == "s3-compatible":
            if not self.s3_endpoint_url:
                raise ValueError("ATTACHMENT_STORAGE_S3_ENDPOINT_URL is required for S3-compatible storage.")
            if self.s3_access_key_id is None or self.s3_secret_access_key is None:
                raise ValueError("Both S3-compatible attachment-storage credentials are required.")
        if self.backend == "local" and not str(self.local_root).strip():
            raise ValueError("ATTACHMENT_STORAGE_LOCAL_ROOT cannot be empty.")
        return self


@lru_cache(maxsize=1)
def get_attachment_storage_config() -> AttachmentStorageConfig:
    """Load attachment storage settings lazily so disabled storage cannot block core startup."""
    return AttachmentStorageConfig()
