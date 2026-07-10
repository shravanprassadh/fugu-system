"""Provider credential testing and atomic lifecycle administration routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.api.dependencies import AdminUser, MasterSession
from fugu.database.models import ProviderCredential
from fugu.database.repositories import ProviderCredentialRepository
from fugu.providers.credential_validation import (
    SUPPORTED_CREDENTIAL_PROVIDERS,
    CredentialValidationResult,
    normalize_credential_provider,
    validate_provider_credential,
)
from fugu.providers.exceptions import ProviderError
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine

provider_admin_router = APIRouter(
    prefix="/api/admin/provider-credentials",
    tags=["provider-administration"],
)


class ProviderCredentialResponse(BaseModel):
    """Non-secret metadata for one active provider key."""

    provider_name: str
    key_version: int
    created_at: datetime
    updated_at: datetime
    last_tested_at: datetime | None
    last_successful_test_at: datetime | None
    last_test_failure_at: datetime | None
    last_test_failure_message: str | None
    configured: bool = True

    @classmethod
    def from_credential(cls, credential: ProviderCredential) -> ProviderCredentialResponse:
        return cls(
            provider_name=credential.provider_name,
            key_version=credential.key_version,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
            last_tested_at=credential.last_tested_at,
            last_successful_test_at=credential.last_successful_test_at,
            last_test_failure_at=credential.last_test_failure_at,
            last_test_failure_message=credential.last_test_failure_message,
        )


class CreateProviderCredentialPayload(BaseModel):
    """Write-only initial provider credential payload."""

    provider_name: str = Field(min_length=2, max_length=100)
    secret: str = Field(min_length=8, max_length=8_192)


class ProviderSecretPayload(BaseModel):
    """Write-only provider candidate secret."""

    secret: str = Field(min_length=8, max_length=8_192)


class ProviderCredentialTestResponse(BaseModel):
    """Sanitized result of an active or candidate credential test."""

    provider_name: str
    valid: bool
    message: str
    tested_at: datetime


class ProviderCredentialMutationResponse(BaseModel):
    """Result of an initial activation or atomic replacement attempt."""

    provider_name: str
    activated: bool
    message: str
    credential: ProviderCredentialResponse | None


def _normalized_supported_provider(provider_name: str) -> str:
    try:
        return normalize_credential_provider(provider_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _credential_or_404(session: AsyncSession, provider_name: str) -> ProviderCredential:
    credential = await ProviderCredentialRepository.get_by_provider(session, provider_name)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider credential not found.",
        )
    return credential


async def _validate_candidate(provider_name: str, secret: str) -> CredentialValidationResult:
    try:
        return await validate_provider_credential(provider_name, secret)
    except ProviderError as exc:
        return CredentialValidationResult(
            provider_name=provider_name,
            valid=False,
            message=str(exc),
        )


def _record_validation(
    credential: ProviderCredential,
    *,
    result: CredentialValidationResult,
    tested_at: datetime,
) -> None:
    credential.last_tested_at = tested_at
    if result.valid:
        credential.last_successful_test_at = tested_at
    else:
        credential.last_test_failure_at = tested_at
        credential.last_test_failure_message = result.message[:4_000]


def _test_response(
    result: CredentialValidationResult,
    *,
    tested_at: datetime,
) -> ProviderCredentialTestResponse:
    return ProviderCredentialTestResponse(
        provider_name=result.provider_name,
        valid=result.valid,
        message=result.message,
        tested_at=tested_at,
    )


@provider_admin_router.get("", response_model=list[ProviderCredentialResponse])
async def list_provider_credentials(
    _: AdminUser,
    session: MasterSession,
) -> list[ProviderCredentialResponse]:
    """List active chat-provider keys without returning plaintext secrets."""
    statement = (
        select(ProviderCredential)
        .where(ProviderCredential.provider_name.in_(sorted(SUPPORTED_CREDENTIAL_PROVIDERS)))
        .order_by(ProviderCredential.provider_name.asc())
    )
    result = await session.scalars(statement)
    return [ProviderCredentialResponse.from_credential(credential) for credential in result.all()]


@provider_admin_router.post("", response_model=ProviderCredentialMutationResponse)
async def create_provider_credential(
    payload: CreateProviderCredentialPayload,
    _: AdminUser,
    session: MasterSession,
) -> ProviderCredentialMutationResponse:
    """Validate and activate the first key for one provider."""
    provider_name = _normalized_supported_provider(payload.provider_name)
    existing = await ProviderCredentialRepository.get_by_provider(session, provider_name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A provider key is already active. Use Change key instead.",
        )

    tested_at = datetime.now(timezone.utc)
    validation = await _validate_candidate(provider_name, payload.secret)
    if not validation.valid:
        return ProviderCredentialMutationResponse(
            provider_name=provider_name,
            activated=False,
            message=validation.message,
            credential=None,
        )

    vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    credential = await vault.store(
        session,
        provider_name=provider_name,
        plaintext_secret=payload.secret,
    )
    _record_validation(credential, result=validation, tested_at=tested_at)
    await session.flush()
    return ProviderCredentialMutationResponse(
        provider_name=provider_name,
        activated=True,
        message="Credential validation succeeded and the provider key is now active.",
        credential=ProviderCredentialResponse.from_credential(credential),
    )


@provider_admin_router.post(
    "/{provider_name}/candidate/test",
    response_model=ProviderCredentialTestResponse,
)
async def test_candidate_provider_credential(
    provider_name: str,
    payload: ProviderSecretPayload,
    _: AdminUser,
) -> ProviderCredentialTestResponse:
    """Test a write-only candidate key without changing the active key."""
    normalized = _normalized_supported_provider(provider_name)
    tested_at = datetime.now(timezone.utc)
    result = await _validate_candidate(normalized, payload.secret)
    return _test_response(result, tested_at=tested_at)


@provider_admin_router.post(
    "/{provider_name}/test",
    response_model=ProviderCredentialTestResponse,
)
async def test_active_provider_credential(
    provider_name: str,
    _: AdminUser,
    session: MasterSession,
) -> ProviderCredentialTestResponse:
    """Test the active key and persist sanitized test history."""
    normalized = _normalized_supported_provider(provider_name)
    credential = await _credential_or_404(session, normalized)
    vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    secret = await vault.retrieve(session, provider_name=normalized)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider credential not found.")

    tested_at = datetime.now(timezone.utc)
    result = await _validate_candidate(normalized, secret)
    _record_validation(credential, result=result, tested_at=tested_at)
    await session.flush()
    return _test_response(result, tested_at=tested_at)


@provider_admin_router.put(
    "/{provider_name}",
    response_model=ProviderCredentialMutationResponse,
)
async def replace_provider_credential(
    provider_name: str,
    payload: ProviderSecretPayload,
    _: AdminUser,
    session: MasterSession,
) -> ProviderCredentialMutationResponse:
    """Validate a candidate and replace the active key only after success."""
    normalized = _normalized_supported_provider(provider_name)
    current = await _credential_or_404(session, normalized)
    tested_at = datetime.now(timezone.utc)
    validation = await _validate_candidate(normalized, payload.secret)
    if not validation.valid:
        _record_validation(current, result=validation, tested_at=tested_at)
        await session.flush()
        return ProviderCredentialMutationResponse(
            provider_name=normalized,
            activated=False,
            message=validation.message,
            credential=ProviderCredentialResponse.from_credential(current),
        )

    vault = ProviderCredentialVault(SymmetricVaultEngine.from_settings())
    credential = await vault.store(
        session,
        provider_name=normalized,
        plaintext_secret=payload.secret,
    )
    _record_validation(credential, result=validation, tested_at=tested_at)
    await session.flush()
    return ProviderCredentialMutationResponse(
        provider_name=normalized,
        activated=True,
        message="Candidate validation succeeded and the active key was replaced atomically.",
        credential=ProviderCredentialResponse.from_credential(credential),
    )


@provider_admin_router.delete(
    "/{provider_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_provider_credential(
    provider_name: str,
    _: AdminUser,
    session: MasterSession,
) -> Response:
    """Delete one active key as an exceptional administrative action."""
    normalized = _normalized_supported_provider(provider_name)
    credential = await _credential_or_404(session, normalized)
    await session.delete(credential)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
