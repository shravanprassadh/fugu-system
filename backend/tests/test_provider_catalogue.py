"""Backend-owned provider and model catalogue tests."""

from __future__ import annotations

import pytest

from fugu.api.routes.execution import PipelineExecutionPayload
from fugu.providers.catalogue import get_provider_catalogue


def test_catalogue_defines_unique_provider_and_model_contracts() -> None:
    catalogue = get_provider_catalogue()
    providers = catalogue.providers

    assert [provider.identifier for provider in providers] == ["openrouter", "nvidia"]
    assert all(provider.authentication_type == "bearer_api_key" for provider in providers)
    assert all(provider.adapter_available for provider in providers)
    assert all(provider.api_base_url.startswith("https://") for provider in providers)

    model_pairs = [(provider.identifier, model.identifier) for provider in providers for model in provider.models]
    assert len(model_pairs) == len(set(model_pairs))
    assert all(model.context_size > 0 for provider in providers for model in provider.models)
    assert all(model.output_limit > 0 for provider in providers for model in provider.models)
    assert all("temperature" in model.supported_parameters for provider in providers for model in provider.models)


def test_catalogue_exposes_conservative_capability_metadata() -> None:
    catalogue = get_provider_catalogue()

    vision = catalogue.model("nvidia", "meta/llama-3.2-11b-vision-instruct")
    reasoning = catalogue.model("nvidia", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    text_only = catalogue.model("openrouter", "openrouter/free")

    assert vision.capabilities.image_understanding is True
    assert reasoning.capabilities.image_understanding is True
    assert reasoning.capabilities.reasoning_support is True
    assert text_only.capabilities.text_generation is True
    assert text_only.capabilities.image_understanding is False
    assert text_only.thinking_budget_minimum is None
    assert text_only.thinking_budget_maximum is None


def test_catalogue_rejects_unknown_and_cross_provider_models() -> None:
    catalogue = get_provider_catalogue()

    with pytest.raises(ValueError, match="Unsupported provider"):
        catalogue.validate_selection("unknown", "openrouter/free")
    with pytest.raises(ValueError, match="not available for provider"):
        catalogue.validate_selection("openrouter", "meta/llama-3.1-8b-instruct")
    with pytest.raises(ValueError, match="not available for provider"):
        catalogue.validate_selection("nvidia", "openrouter/free")


def test_execution_override_uses_catalogue_validation() -> None:
    accepted = PipelineExecutionPayload(
        prompt="Explain this design.",
        provider_type=" NVIDIA ",
        model_identifier="meta/llama-3.1-8b-instruct",
    )
    assert accepted.provider_type == "nvidia"
    assert accepted.model_identifier == "meta/llama-3.1-8b-instruct"

    with pytest.raises(ValueError, match="not available for provider"):
        PipelineExecutionPayload(
            prompt="Explain this design.",
            provider_type="openrouter",
            model_identifier="meta/llama-3.1-8b-instruct",
        )
