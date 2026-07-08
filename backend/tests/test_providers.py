"""Provider registry, streaming, and typed-failure tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
<<<<<<< Updated upstream
=======

>>>>>>> Stashed changes
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.exceptions import (
    ProviderAlreadyRegisteredError,
    ProviderAuthenticationError,
    ProviderNotRegisteredError,
    ProviderRateLimitError,
    ProviderResponseMalformedError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from fugu.providers.openrouter import (
    OPENROUTER_CHAT_COMPLETIONS_URL,
    OpenRouterStreamProvider,
    ServerSentEventParser,
)
from fugu.providers.registry import ProviderRegistry


class FakeProvider(ExecutionProvider):
    """Minimal provider implementation used to validate registry contracts."""

    async def generate_token_stream(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[str]:
        yield request.prompt_content


class AlternateFakeProvider(FakeProvider):
    """Distinct provider class used to test explicit registry replacement."""


class ChunkedByteStream(httpx.AsyncByteStream):
    """Yield deterministic byte fragments to exercise incremental SSE parsing."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


AsyncTransportHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _request() -> ProviderRequest:
    return ProviderRequest(
        prompt_content="Explain the modular kernel.",
        system_directives="Answer precisely.",
        credential_token="provider-secret",
        model_identifier="openai/gpt-test",
    )


def _client(handler: AsyncTransportHandler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _collect(provider: OpenRouterStreamProvider) -> list[str]:
    return [token async for token in provider.generate_token_stream(_request())]


def test_provider_registry_registration_resolution_and_duplicates() -> None:
    """Registry names are normalized and duplicate behavior is explicit."""
    registry = ProviderRegistry()
    registry.register(" OpenRouter ", FakeProvider)

    assert registry.registered_names() == ("openrouter",)
    assert isinstance(registry.resolve("OPENROUTER"), FakeProvider)

    with pytest.raises(ProviderAlreadyRegisteredError):
        registry.register("openrouter", AlternateFakeProvider)

    registry.register("openrouter", AlternateFakeProvider, replace=True)
    assert isinstance(registry.resolve("openrouter"), AlternateFakeProvider)


def test_provider_registry_rejects_unknown_and_blank_names() -> None:
    """Unknown provider resolution and blank identifiers fail clearly."""
    registry = ProviderRegistry()

    with pytest.raises(ProviderNotRegisteredError):
        registry.resolve("missing-provider")
    with pytest.raises(ValueError):
        registry.register(" ", FakeProvider)


def test_sse_parser_ignores_metadata_and_supports_multiline_data() -> None:
    """Comments and metadata are ignored while data lines form one event."""
    parser = ServerSentEventParser()

    events = parser.feed(
<<<<<<< Updated upstream
        ": keepalive\r\nevent: message\r\nid: 42\r\n"
        'data: {"choices":\r\ndata: [{"delta": {"content": "ok"}}]}\r\n\r\n'
=======
        ': keepalive\r\nevent: message\r\nid: 42\r\ndata: {"choices":\r\ndata: [{"delta": {"content": "ok"}}]}\r\n\r\n'
>>>>>>> Stashed changes
    )

    assert events == ['{"choices":\n[{"delta": {"content": "ok"}}]}']


@pytest.mark.asyncio
async def test_openrouter_reconstructs_fragmented_sse_chunks() -> None:
    """JSON and control markers split across chunks are reconstructed safely."""
    chunks = [
        b'data: {"choices":[{"delta":{"content":"Sov',
        b'ereign"}}]}\r\n\r\ndata: {"choices":[{"delta":{"content":" Kernel"}}]}\n',
        b"\ndata: [DO",
        b"NE]\n\n",
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == OPENROUTER_CHAT_COMPLETIONS_URL
        assert request.headers["authorization"] == "Bearer provider-secret"
        return httpx.Response(200, stream=ChunkedByteStream(chunks))

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        assert await _collect(provider) == ["Sovereign", " Kernel"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_reuses_injected_client() -> None:
    """One provider instance can issue multiple requests through the same client."""
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            stream=ChunkedByteStream([b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n']),
        )

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        assert await _collect(provider) == ["ok"]
        assert await _collect(provider) == ["ok"]
        await provider.aclose()
        assert not client.is_closed
        assert calls == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (408, ProviderTimeoutError),
        (504, ProviderTimeoutError),
        (500, ProviderTransportError),
    ],
)
async def test_openrouter_maps_http_statuses(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    """Provider HTTP statuses map to stable typed application failures."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        with pytest.raises(expected_error):
            await _collect(provider)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_maps_network_timeout() -> None:
    """HTTPX timeout exceptions become ProviderTimeoutError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        with pytest.raises(ProviderTimeoutError):
            await _collect(provider)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_maps_transport_failure() -> None:
    """Connection failures become ProviderTransportError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure", request=request)

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        with pytest.raises(ProviderTransportError):
            await _collect(provider)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_rejects_invalid_json_payload() -> None:
    """Invalid SSE JSON is raised as a typed malformed-response error."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=ChunkedByteStream([b"data: {invalid-json}\n\n"]),
        )

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        with pytest.raises(ProviderResponseMalformedError):
            await _collect(provider)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_openrouter_ignores_non_data_sse_frames() -> None:
    """SSE comments and metadata frames do not crash or produce tokens."""

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=ChunkedByteStream([b": keepalive\n\nevent: message\nid: 7\n\ndata: [DONE]\n\n"]),
        )

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        assert await _collect(provider) == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected_error"),
    [
        (401, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (504, ProviderTimeoutError),
        (500, ProviderTransportError),
    ],
)
async def test_openrouter_maps_vendor_error_frames(
    code: int,
    expected_error: type[Exception],
) -> None:
    """Vendor-side error objects inside successful streams map to typed errors."""
    payload = f'data: {{"error":{{"code":{code},"message":"provider failure"}}}}\n\n'

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=ChunkedByteStream([payload.encode("utf-8")]),
        )

    client = _client(handler)
    provider = OpenRouterStreamProvider(client=client)
    try:
        with pytest.raises(expected_error):
            await _collect(provider)
    finally:
        await client.aclose()
