"""Provider credential validation and failure-mapping tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
import pytest

from fugu.providers.credential_validation import (
    NVIDIA_CREDENTIAL_TEST_URL,
    OPENROUTER_CREDENTIAL_TEST_URL,
    normalize_credential_provider,
    validate_provider_credential,
)
from fugu.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderResponseMalformedError,
    ProviderTimeoutError,
)

AsyncTransportHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _client(handler: AsyncTransportHandler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_credential_provider_normalization_rejects_unknown_values() -> None:
    assert normalize_credential_provider(" OpenRouter ") == "openrouter"
    assert normalize_credential_provider("NVIDIA") == "nvidia"
    with pytest.raises(ValueError, match="Unsupported provider"):
        normalize_credential_provider("unknown")


@pytest.mark.asyncio
async def test_openrouter_credential_probe_uses_read_only_key_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == OPENROUTER_CREDENTIAL_TEST_URL
        assert request.headers["authorization"] == "Bearer candidate-secret"
        return httpx.Response(200, json={"data": {"label": "Fugu"}})

    client = _client(handler)
    try:
        result = await validate_provider_credential(
            "openrouter",
            "candidate-secret",
            client=client,
        )
    finally:
        await client.aclose()

    assert result.valid is True
    assert result.provider_name == "openrouter"


@pytest.mark.asyncio
async def test_nvidia_credential_probe_uses_models_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == NVIDIA_CREDENTIAL_TEST_URL
        assert request.headers["authorization"] == "Bearer candidate-secret"
        return httpx.Response(200, json={"data": [{"id": "meta/llama"}]})

    client = _client(handler)
    try:
        result = await validate_provider_credential(
            "nvidia",
            "candidate-secret",
            client=client,
        )
    finally:
        await client.aclose()

    assert result.valid is True
    assert result.provider_name == "nvidia"


@pytest.mark.asyncio
async def test_credential_probe_maps_authentication_failure() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = _client(handler)
    try:
        with pytest.raises(ProviderAuthenticationError, match="rejected"):
            await validate_provider_credential("openrouter", "candidate-secret", client=client)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_credential_probe_rejects_malformed_success_payload() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    client = _client(handler)
    try:
        with pytest.raises(ProviderResponseMalformedError, match="malformed"):
            await validate_provider_credential("openrouter", "candidate-secret", client=client)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_credential_probe_maps_network_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    client = _client(handler)
    try:
        with pytest.raises(ProviderTimeoutError, match="timeout"):
            await validate_provider_credential("nvidia", "candidate-secret", client=client)
    finally:
        await client.aclose()
