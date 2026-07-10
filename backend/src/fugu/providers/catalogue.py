"""Authoritative provider and model capability catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

NVIDIA_MODEL_IDS = (
    "01-ai/yi-large",
    "abacusai/dracarys-llama-3.1-70b-instruct",
    "ai21labs/jamba-1.5-large-instruct",
    "aisingapore/sea-lion-7b-instruct",
    "bytedance/seed-oss-36b-instruct",
    "databricks/dbrx-instruct",
    "deepseek-ai/deepseek-coder-6.7b-instruct",
    "deepseek-ai/deepseek-v4-flash",
    "deepseek-ai/deepseek-v4-pro",
    "google/codegemma-1.1-7b",
    "google/codegemma-7b",
    "google/gemma-2-2b-it",
    "google/gemma-3-12b-it",
    "google/gemma-3-4b-it",
    "google/gemma-3n-e2b-it",
    "google/gemma-3n-e4b-it",
    "google/gemma-4-31b-it",
    "ibm/granite-3.0-3b-a800m-instruct",
    "ibm/granite-3.0-8b-instruct",
    "ibm/granite-34b-code-instruct",
    "ibm/granite-8b-code-instruct",
    "meta/codellama-70b",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.2-1b-instruct",
    "meta/llama-3.2-3b-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.3-70b-instruct",
    "meta/llama-4-maverick-17b-128e-instruct",
    "meta/llama2-70b",
    "microsoft/phi-3-vision-128k-instruct",
    "microsoft/phi-3.5-moe-instruct",
    "microsoft/phi-4-mini-instruct",
    "microsoft/phi-4-multimodal-instruct",
    "minimaxai/minimax-m2.7",
    "minimaxai/minimax-m3",
    "mistralai/codestral-22b-instruct-v0.1",
    "mistralai/ministral-14b-instruct-2512",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mistral-large",
    "mistralai/mistral-large-2-instruct",
    "mistralai/mistral-large-3-675b-instruct-2512",
    "mistralai/mistral-medium-3.5-128b",
    "mistralai/mistral-nemotron",
    "mistralai/mistral-small-4-119b-2603",
    "mistralai/mixtral-8x22b-v0.1",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    "moonshotai/kimi-k2.6",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "nvidia/cosmos-reason2-8b",
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/llama3-chatqa-1.5-70b",
    "nvidia/mistral-nemo-minitron-8b-8k-instruct",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-4-340b-instruct",
    "nvidia/nemotron-mini-4b-instruct",
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-next-80b-a3b-instruct",
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3.5-397b-a17b",
    "sarvamai/sarvam-m",
    "stepfun-ai/step-3.5-flash",
    "stepfun-ai/step-3.7-flash",
    "stockmark/stockmark-2-100b-instruct",
    "upstage/solar-10.7b-instruct",
    "writer/palmyra-creative-122b",
    "writer/palmyra-fin-70b-32k",
    "writer/palmyra-med-70b",
    "writer/palmyra-med-70b-32k",
    "z-ai/glm-5.2",
    "zyphra/zamba2-7b-instruct",
)


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Execution capabilities used to validate pipeline requirements."""

    text_generation: bool
    image_understanding: bool
    document_input: bool
    tool_support: bool
    reasoning_support: bool


@dataclass(frozen=True, slots=True)
class NumericParameterRange:
    """Inclusive numeric parameter contract."""

    minimum: float
    maximum: float
    default: float


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """One selectable model and its conservative execution contract."""

    identifier: str
    display_name: str
    capabilities: ModelCapabilities
    context_size: int
    output_limit: int
    temperature: NumericParameterRange | None
    thinking_budget_minimum: int | None
    thinking_budget_maximum: int | None
    supported_parameters: tuple[str, ...]
    availability_status: str


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """One provider adapter and its backend-owned model catalogue."""

    identifier: str
    display_name: str
    authentication_type: str
    adapter_available: bool
    health_status: str
    api_base_url: str
    capabilities: ModelCapabilities
    models: tuple[ModelDefinition, ...]


def _display_name(model_identifier: str) -> str:
    _, _, raw_name = model_identifier.rpartition("/")
    value = raw_name or model_identifier
    return " ".join(part.capitalize() for part in value.replace(".", "-").split("-") if part)


def _context_size(model_identifier: str) -> int:
    lowered = model_identifier.lower()
    if "128k" in lowered:
        return 131_072
    if "32k" in lowered:
        return 32_768
    if "8k" in lowered:
        return 8_192
    return 32_768


def _capabilities(model_identifier: str) -> ModelCapabilities:
    lowered = model_identifier.lower()
    vision = any(token in lowered for token in ("vision", "multimodal", "omni"))
    reasoning = any(token in lowered for token in ("reasoning", "reason2", "deepseek-v4-pro"))
    return ModelCapabilities(
        text_generation=True,
        image_understanding=vision,
        document_input=False,
        tool_support=False,
        reasoning_support=reasoning,
    )


def _model(model_identifier: str) -> ModelDefinition:
    capabilities = _capabilities(model_identifier)
    return ModelDefinition(
        identifier=model_identifier,
        display_name=_display_name(model_identifier),
        capabilities=capabilities,
        context_size=_context_size(model_identifier),
        output_limit=4_096,
        temperature=NumericParameterRange(minimum=0.0, maximum=2.0, default=0.7),
        thinking_budget_minimum=None,
        thinking_budget_maximum=None,
        supported_parameters=("temperature", "max_output_tokens"),
        availability_status="available",
    )


def _aggregate_capabilities(models: tuple[ModelDefinition, ...]) -> ModelCapabilities:
    return ModelCapabilities(
        text_generation=any(model.capabilities.text_generation for model in models),
        image_understanding=any(model.capabilities.image_understanding for model in models),
        document_input=any(model.capabilities.document_input for model in models),
        tool_support=any(model.capabilities.tool_support for model in models),
        reasoning_support=any(model.capabilities.reasoning_support for model in models),
    )


class ProviderCatalogue:
    """Immutable provider/model system of record and validation service."""

    def __init__(self, providers: tuple[ProviderDefinition, ...]) -> None:
        self._providers = providers
        self._provider_index = {provider.identifier: provider for provider in providers}
        self._model_index = {
            (provider.identifier, model.identifier): model
            for provider in providers
            for model in provider.models
        }

    @property
    def providers(self) -> tuple[ProviderDefinition, ...]:
        return self._providers

    def provider(self, provider_identifier: str) -> ProviderDefinition:
        normalized = provider_identifier.strip().lower()
        provider = self._provider_index.get(normalized)
        if provider is None:
            supported = ", ".join(sorted(self._provider_index))
            raise ValueError(f"Unsupported provider {provider_identifier!r}. Supported providers: {supported}.")
        return provider

    def model(self, provider_identifier: str, model_identifier: str) -> ModelDefinition:
        provider = self.provider(provider_identifier)
        normalized_model = model_identifier.strip()
        model = self._model_index.get((provider.identifier, normalized_model))
        if model is None:
            raise ValueError(
                f"Model {model_identifier!r} is not available for provider {provider.identifier!r}."
            )
        return model

    def validate_selection(self, provider_identifier: str, model_identifier: str) -> ModelDefinition:
        provider = self.provider(provider_identifier)
        if not provider.adapter_available or provider.health_status != "available":
            raise ValueError(f"Provider {provider.identifier!r} is not currently available.")
        model = self.model(provider.identifier, model_identifier)
        if model.availability_status != "available":
            raise ValueError(
                f"Model {model.identifier!r} is not currently available for provider {provider.identifier!r}."
            )
        return model


@lru_cache(maxsize=1)
def get_provider_catalogue() -> ProviderCatalogue:
    """Return the immutable application provider/model catalogue."""
    openrouter_models = (
        ModelDefinition(
            identifier="openrouter/free",
            display_name="OpenRouter Free Tier",
            capabilities=ModelCapabilities(
                text_generation=True,
                image_understanding=False,
                document_input=False,
                tool_support=False,
                reasoning_support=False,
            ),
            context_size=32_768,
            output_limit=4_096,
            temperature=NumericParameterRange(minimum=0.0, maximum=2.0, default=0.7),
            thinking_budget_minimum=None,
            thinking_budget_maximum=None,
            supported_parameters=("temperature", "max_output_tokens"),
            availability_status="available",
        ),
    )
    nvidia_models = tuple(_model(identifier) for identifier in NVIDIA_MODEL_IDS)
    providers = (
        ProviderDefinition(
            identifier="openrouter",
            display_name="OpenRouter",
            authentication_type="bearer_api_key",
            adapter_available=True,
            health_status="available",
            api_base_url="https://openrouter.ai/api/v1",
            capabilities=_aggregate_capabilities(openrouter_models),
            models=openrouter_models,
        ),
        ProviderDefinition(
            identifier="nvidia",
            display_name="NVIDIA",
            authentication_type="bearer_api_key",
            adapter_available=True,
            health_status="available",
            api_base_url="https://integrate.api.nvidia.com/v1",
            capabilities=_aggregate_capabilities(nvidia_models),
            models=nvidia_models,
        ),
    )
    return ProviderCatalogue(providers)
