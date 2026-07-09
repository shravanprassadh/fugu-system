"""Tests for Render control-plane diagnostics."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from fugu.api.routes import render_admin
from fugu.boot.config import get_settings

_VALID_ENVIRONMENT = {
    "MASTER_ROUTER_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db1",
    "METADATA_SIDEBAR_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db2",
    "TRANSACTIONAL_LOGS_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db3",
    "SYSTEM_SESSION_SECRET": "SessionSigningSecretWithAtLeastThirtyTwoCharacters",
    "VAULT_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "ALLOWED_ORIGINS": "https://myfugu.vercel.app",
}


class _UnauthorizedRenderClient:
    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def __aenter__(self) -> _UnauthorizedRenderClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def request(self, *_: Any, **__: Any) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})


@pytest.fixture(autouse=True)
def configure_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _VALID_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_render_request_reports_external_authorization_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render_admin.httpx, "AsyncClient", _UnauthorizedRenderClient)

    with pytest.raises(HTTPException) as exception_info:
        await render_admin._render_request("GET", "/services/srv-example/env-vars?limit=1", api_token="invalid-token")

    assert exception_info.value.status_code == 400
    detail = str(exception_info.value.detail)
    assert "Stored Render API credentials were rejected by Render" in detail
    assert "Click Change in Render control plane" in detail
    assert "Render API returned HTTP 401: Unauthorized" in detail
