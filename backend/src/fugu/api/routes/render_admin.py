"""Render deployment administration routes."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.api.dependencies import AdminUser, MasterSession
from fugu.boot.config import get_settings
from fugu.security.encryption import ProviderCredentialVault, SymmetricVaultEngine

render_admin_router = APIRouter(prefix="/api/admin/render", tags=["render-administration"])
_RENDER_CONFIG_PROVIDER = "render_control_plane"
_RENDER_API_BASE_URL = "https://api.render.com/v1"
_RENDER_AUTH_STATUS_CODES = {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
_RENDER_DATABASE_ENV_KEYS = {
    "MASTER_ROUTER_DB_URL": "master_router_db_url",
    "METADATA_SIDEBAR_DB_URL": "metadata_sidebar_db_url",
    "TRANSACTIONAL_LOGS_DB_URL": "transactional_logs_db_url",
}
_RENDER_DATABASE_TARGET_ENV_KEYS = {
    "master": "MASTER_ROUTER_DB_URL",
    "metadata": "METADATA_SIDEBAR_DB_URL",
    "logs": "TRANSACTIONAL_LOGS_DB_URL",
}


class RenderConfigPayload(BaseModel):
    """Write-only Render API configuration."""

    service_id: str = Field(min_length=3, max_length=255)
    api_token: str | None = Field(default=None, min_length=20, max_length=8_192)


class RenderConfigResponse(BaseModel):
    """Sanitized Render integration status."""

    configured: bool
    service_id: str | None = None
    has_api_token: bool = False


class RenderDatabaseEnvPayload(BaseModel):
    """Database URLs that should be persisted into Render service env vars."""

    master_router_db_url: str = Field(min_length=20, max_length=4_096)
    metadata_sidebar_db_url: str = Field(min_length=20, max_length=4_096)
    transactional_logs_db_url: str = Field(min_length=20, max_length=4_096)
    trigger_deploy: bool = True


class RenderSingleDatabaseEnvPayload(BaseModel):
    """One database URL that should be persisted into one Render service env var."""

    database_url: str = Field(min_length=20, max_length=4_096)
    trigger_deploy: bool = True


class RenderEnvUpdateResult(BaseModel):
    """Sanitized Render environment update result."""

    status: Literal["configured", "updated"]
    service_id: str
    updated_env_keys: list[str]
    deploy_triggered: bool
    deploy_id: str | None = None
    note: str


class _RenderConfig(BaseModel):
    service_id: str
    api_token: str


async def _vault() -> ProviderCredentialVault:
    return ProviderCredentialVault(SymmetricVaultEngine.from_settings())


async def _read_render_config(session: AsyncSession) -> _RenderConfig | None:
    vault = await _vault()
    encrypted_config = await vault.retrieve(session, provider_name=_RENDER_CONFIG_PROVIDER)
    if encrypted_config is None:
        return None
    try:
        payload = json.loads(encrypted_config)
        return _RenderConfig.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored Render integration configuration is malformed.",
        ) from exc


async def _write_render_config(session: AsyncSession, config: _RenderConfig) -> None:
    vault = await _vault()
    await vault.store(
        session,
        provider_name=_RENDER_CONFIG_PROVIDER,
        plaintext_secret=config.model_dump_json(),
    )


def _render_headers(api_token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def _render_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"Render API returned HTTP {response.status_code}."
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error") or payload.get("detail")
        if isinstance(message, str):
            return message
    return f"Render API returned HTTP {response.status_code}."


def _render_admin_error_detail(response: httpx.Response) -> str:
    render_message = _render_error_message(response)
    if response.status_code in _RENDER_AUTH_STATUS_CODES:
        return (
            "Stored Render API credentials were rejected by Render. "
            "Click Change in Render control plane and save a current Render API token "
            "that can access the configured service. "
            f"Render API returned HTTP {response.status_code}: {render_message}"
        )
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return (
            "The configured Render service ID was not found for the stored Render API token. "
            "Click Change in Render control plane and verify the service ID belongs to "
            "the same Render account as the API token. "
            f"Render API returned HTTP {response.status_code}: {render_message}"
        )
    return f"Render API request failed with HTTP {response.status_code}: {render_message}"


async def _render_request(
    method: str,
    path: str,
    *,
    api_token: str,
    json_body: Any | None = None,
) -> Any:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.network_request_timeout) as client:
        response = await client.request(
            method,
            f"{_RENDER_API_BASE_URL}{path}",
            headers=_render_headers(api_token),
            json=json_body,
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_render_admin_error_detail(response),
        )
    if not response.content:
        return None
    return response.json()


async def _require_render_config(session: AsyncSession) -> _RenderConfig:
    config = await _read_render_config(session)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Render integration is not configured yet.",
        )
    return config


def _normalize_database_target(target: str) -> str:
    normalized = target.strip().lower()
    if normalized not in _RENDER_DATABASE_TARGET_ENV_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown database target. Use master, metadata, or logs.",
        )
    return normalized


async def _upsert_render_env_var(config: _RenderConfig, key: str, value: str) -> None:
    await _render_request(
        "PUT",
        f"/services/{config.service_id}/env-vars/{key}",
        api_token=config.api_token,
        json_body={"value": value},
    )


async def _trigger_render_deploy(config: _RenderConfig) -> str | None:
    payload = await _render_request(
        "POST",
        f"/services/{config.service_id}/deploys",
        api_token=config.api_token,
        json_body={},
    )
    if isinstance(payload, dict):
        deploy_id = payload.get("id")
        return deploy_id if isinstance(deploy_id, str) else None
    return None


@render_admin_router.get("/config", response_model=RenderConfigResponse)
async def get_render_config(
    _: AdminUser,
    session: MasterSession,
) -> RenderConfigResponse:
    """Return sanitized Render integration status."""
    config = await _read_render_config(session)
    if config is None:
        return RenderConfigResponse(configured=False)
    return RenderConfigResponse(configured=True, service_id=config.service_id, has_api_token=True)


@render_admin_router.post("/config", response_model=RenderConfigResponse)
async def save_render_config(
    payload: RenderConfigPayload,
    _: AdminUser,
    session: MasterSession,
) -> RenderConfigResponse:
    """Store or update the Render API token and service id without returning the token."""
    existing = await _read_render_config(session)
    api_token = payload.api_token or existing.api_token if existing is not None else payload.api_token
    if api_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Render API token is required the first time you configure Render integration.",
        )
    config = _RenderConfig(service_id=payload.service_id.strip(), api_token=api_token.strip())
    await _write_render_config(session, config)
    return RenderConfigResponse(configured=True, service_id=config.service_id, has_api_token=True)


@render_admin_router.post("/config/test", response_model=RenderConfigResponse)
async def test_render_config(
    _: AdminUser,
    session: MasterSession,
) -> RenderConfigResponse:
    """Validate the stored Render API token and service id."""
    config = await _require_render_config(session)
    await _render_request(
        "GET",
        f"/services/{config.service_id}/env-vars?limit=1",
        api_token=config.api_token,
    )
    return RenderConfigResponse(configured=True, service_id=config.service_id, has_api_token=True)


@render_admin_router.post("/database-env", response_model=RenderEnvUpdateResult)
async def persist_database_env_to_render(
    payload: RenderDatabaseEnvPayload,
    _: AdminUser,
    session: MasterSession,
) -> RenderEnvUpdateResult:
    """Persist database URLs to Render env vars and optionally trigger a deploy."""
    config = await _require_render_config(session)
    payload_values = payload.model_dump()
    for render_key, payload_key in _RENDER_DATABASE_ENV_KEYS.items():
        await _upsert_render_env_var(config, render_key, str(payload_values[payload_key]))

    deploy_id = await _trigger_render_deploy(config) if payload.trigger_deploy else None
    return RenderEnvUpdateResult(
        status="updated",
        service_id=config.service_id,
        updated_env_keys=list(_RENDER_DATABASE_ENV_KEYS.keys()),
        deploy_triggered=payload.trigger_deploy,
        deploy_id=deploy_id,
        note=(
            "Render environment variables were updated and a deploy was triggered. "
            "The restarted service will load the persisted database URLs."
            if payload.trigger_deploy
            else "Render environment variables were updated. Trigger a deploy before expecting them to take effect."
        ),
    )


@render_admin_router.post("/database-env/{target}", response_model=RenderEnvUpdateResult)
async def persist_single_database_env_to_render(
    target: str,
    payload: RenderSingleDatabaseEnvPayload,
    _: AdminUser,
    session: MasterSession,
) -> RenderEnvUpdateResult:
    """Persist one database URL to one Render env var and optionally trigger a deploy."""
    normalized_target = _normalize_database_target(target)
    render_key = _RENDER_DATABASE_TARGET_ENV_KEYS[normalized_target]
    config = await _require_render_config(session)
    await _upsert_render_env_var(config, render_key, payload.database_url)
    deploy_id = await _trigger_render_deploy(config) if payload.trigger_deploy else None
    return RenderEnvUpdateResult(
        status="updated",
        service_id=config.service_id,
        updated_env_keys=[render_key],
        deploy_triggered=payload.trigger_deploy,
        deploy_id=deploy_id,
        note=(
            f"{render_key} was updated in Render and a deploy was triggered. "
            "The restarted service will load the new database URL."
            if payload.trigger_deploy
            else f"{render_key} was updated in Render. Trigger a deploy before expecting it to take effect."
        ),
    )
