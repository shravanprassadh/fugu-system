"""CORS regression coverage for atomic provider key replacement."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from fugu.main import create_app
from tests.test_production import FakeRuntimeRegistry, build_settings


@pytest.mark.asyncio
async def test_cors_allows_provider_key_put_from_configured_origin() -> None:
    settings = build_settings()
    registry = FakeRuntimeRegistry()
    application = create_app(settings=settings, session_registry=registry)  # type: ignore[arg-type]
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/admin/provider-credentials/openrouter",
            headers={
                "Origin": "https://studio.example.com",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://studio.example.com"
    assert "PUT" in response.headers["access-control-allow-methods"]
