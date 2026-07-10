"""Model parameter validation and propagation tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from fugu.api.routes.execution import PipelineExecutionPayload
from fugu.execution.kernel import PipelineExecutionKernel
from fugu.execution.models import PipelineStepDefinition
from fugu.providers.base import ProviderRequest
from fugu.providers.nvidia import NvidiaStreamProvider
from fugu.providers.openrouter import OpenRouterStreamProvider
from fugu.providers.parameters import validate_model_parameters


class DoneStream(httpx.AsyncByteStream):
    """Return one deterministic provider completion marker."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: [DONE]\n\n"


AsyncTransportHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _client(handler: AsyncTransportHandler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _provider_request() -> ProviderRequest:
    return ProviderRequest(
        prompt_content="Explain the design.",
        system_directives="Be precise.",
        credential_token="provider-secret",
        model_identifier="openrouter/free",
        temperature=0.4,
        max_output_tokens=1_024,
    )


def test_model_parameter_contract_accepts_supported_ranges() -> None:
    parameters = validate_model_parameters(
        "openrouter",
        "openrouter/free",
        temperature=0.4,
        max_output_tokens=1_024,
    )

    assert parameters.temperature == 0.4
    assert parameters.max_output_tokens == 1_024
    assert parameters.thinking_budget is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"temperature": -0.1}, "Temperature"),
        ({"temperature": 2.1}, "Temperature"),
        ({"max_output_tokens": 0}, "Output limit"),
        ({"max_output_tokens": 4_097}, "Output limit"),
        ({"thinking_budget": 256}, "does not support thinking_budget"),
    ],
)
def test_model_parameter_contract_rejects_invalid_or_unsupported_values(
    kwargs: dict[str, float | int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_model_parameters("openrouter", "openrouter/free", **kwargs)


def test_execution_payload_requires_model_pair_for_parameters() -> None:
    with pytest.raises(ValueError, match="required when model parameters are supplied"):
        PipelineExecutionPayload(prompt="Explain the design.", temperature=0.4)

    payload = PipelineExecutionPayload(
        prompt="Explain the design.",
        provider_type="openrouter",
        model_identifier="openrouter/free",
        temperature=0.4,
        max_output_tokens=1_024,
    )
    assert payload.temperature == 0.4
    assert payload.max_output_tokens == 1_024


def test_terminal_override_carries_validated_parameters_only_to_terminal_step() -> None:
    steps = (
        PipelineStepDefinition(
            name="reader",
            sequence_order_position=1,
            provider_type="nvidia",
            model_identifier="meta/llama-3.1-8b-instruct",
            system_directives="Read.",
            prerequisites=(),
            is_terminal=False,
        ),
        PipelineStepDefinition(
            name="consolidator",
            sequence_order_position=2,
            provider_type="nvidia",
            model_identifier="meta/llama-3.1-8b-instruct",
            system_directives="Answer.",
            prerequisites=("reader",),
            is_terminal=True,
        ),
    )

    updated = PipelineExecutionKernel._apply_terminal_model_override(
        ordered_steps=steps,
        terminal_step_name="consolidator",
        selected_provider_type="openrouter",
        selected_model_identifier="openrouter/free",
        selected_temperature=0.4,
        selected_max_output_tokens=1_024,
        selected_thinking_budget=None,
    )

    assert updated[0] == steps[0]
    assert updated[1].provider_type == "openrouter"
    assert updated[1].model_identifier == "openrouter/free"
    assert updated[1].temperature == 0.4
    assert updated[1].max_output_tokens == 1_024


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_class", [OpenRouterStreamProvider, NvidiaStreamProvider])
async def test_openai_compatible_adapters_send_validated_parameters(
    provider_class: type[OpenRouterStreamProvider] | type[NvidiaStreamProvider],
) -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, stream=DoneStream())

    client = _client(handler)
    provider = provider_class(client=client)
    request = _provider_request()
    if provider_class is NvidiaStreamProvider:
        request = ProviderRequest(
            prompt_content=request.prompt_content,
            system_directives=request.system_directives,
            credential_token=request.credential_token,
            model_identifier="meta/llama-3.1-8b-instruct",
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )
    try:
        assert [token async for token in provider.generate_token_stream(request)] == []
    finally:
        await client.aclose()

    assert captured["temperature"] == 0.4
    assert captured["max_tokens"] == 1_024
    assert "thinking_budget" not in captured
