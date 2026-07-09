"""Thread-memory summarizer credential administration routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from fugu.api.dependencies import AdminUser, MasterSession
from fugu.database.models import ProviderCredential
from fugu.memory.summarizer import MEMORY_CREDENTIAL_PROVIDER_NAME, MEMORY_MODEL_IDENTIFIER, MEMORY_PROVIDER_LABEL
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine

thread_memory_admin_router = APIRouter(
    prefix="/api/admin/thread-memory",
    tags=["thread-memory-administration"],
)


class ThreadMemoryConfigResponse(BaseModel):
    """Non-secret status for the dedicated thread-memory Google AI Studio key."""

    configured: bool
    provider_name: str
    model_identifier: str
    credential_key_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_credential(cls, credential: ProviderCredential | None) -> ThreadMemoryConfigResponse:
        return cls(
            configured=credential is not None,
            provider_name=MEMORY_PROVIDER_LABEL,
            model_identifier=MEMORY_MODEL_IDENTIFIER,
            credential_key_version=credential.key_version if credential is not None else None,
            created_at=credential.created_at if credential is not None else None,
            updated_at=credential.updated_at if credential is not None else None,
        )


class ThreadMemoryCredentialPayload(BaseModel):
    """Write-only Google AI Studio key for thread memory."""

    api_key: str = Field(min_length=8, max_length=8_192)


async def _get_memory_credential(session: MasterSession) -> ProviderCredential | None:
    result = await session.scalars(
        select(ProviderCredential).where(ProviderCredential.provider_name == MEMORY_CREDENTIAL_PROVIDER_NAME)
    )
    return result.one_or_none()


@thread_memory_admin_router.get("/config", response_model=ThreadMemoryConfigResponse)
async def get_thread_memory_config(
    _: AdminUser,
    session: MasterSession,
) -> ThreadMemoryConfigResponse:
    """Return whether the dedicated thread-memory Google AI Studio key is configured."""
    credential = await _get_memory_credential(session)
    return ThreadMemoryConfigResponse.from_credential(credential)


@thread_memory_admin_router.post("/config", response_model=ThreadMemoryConfigResponse)
async def save_thread_memory_config(
    payload: ThreadMemoryCredentialPayload,
    _: AdminUser,
    session: MasterSession,
) -> ThreadMemoryConfigResponse:
    """Create or rotate the dedicated thread-memory Google AI Studio key."""
    vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    credential = await vault.store(
        session,
        provider_name=MEMORY_CREDENTIAL_PROVIDER_NAME,
        plaintext_secret=payload.api_key,
    )
    return ThreadMemoryConfigResponse.from_credential(credential)


@thread_memory_admin_router.delete("/config", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_thread_memory_config(
    _: AdminUser,
    session: MasterSession,
) -> Response:
    """Delete the dedicated thread-memory Google AI Studio key."""
    credential = await _get_memory_credential(session)
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread memory key is not configured.")
    await session.delete(credential)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
