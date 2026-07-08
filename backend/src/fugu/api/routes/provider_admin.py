"""Provider credential lifecycle administration routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from fugu.api.dependencies import AdminUser, MasterSession
from fugu.database.models import ProviderCredential

provider_admin_router = APIRouter(
    prefix="/api/admin/provider-credentials",
    tags=["provider-administration"],
)
_SUPPORTED_PROVIDER_NAMES = {"openrouter", "nvidia"}


def _normalized_supported_provider(provider_name: str) -> str:
    normalized = provider_name.strip().lower()
    if normalized not in _SUPPORTED_PROVIDER_NAMES:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDER_NAMES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider {provider_name!r}. Supported providers: {supported}.",
        )
    return normalized


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
    """Delete one configured provider credential so a new key can be added later."""
    normalized = _normalized_supported_provider(provider_name)
    result = await session.scalars(
        select(ProviderCredential).where(ProviderCredential.provider_name == normalized)
    )
    credential = result.first()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider credential not found.")
    await session.delete(credential)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
