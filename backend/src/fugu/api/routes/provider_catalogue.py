"""Authenticated provider and model capability catalogue routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fugu.api.dependencies import CurrentUser
from fugu.providers.catalogue import (
    ModelCapabilities,
    ModelDefinition,
    NumericParameterRange,
    ProviderDefinition,
    get_provider_catalogue,
)

provider_catalogue_router = APIRouter(prefix="/api/providers", tags=["providers"])


class ModelCapabilitiesResponse(BaseModel):
    text_generation: bool
    image_understanding: bool
    document_input: bool
    tool_support: bool
    reasoning_support: bool

    @classmethod
    def from_capabilities(cls, capabilities: ModelCapabilities) -> ModelCapabilitiesResponse:
        return cls(
            text_generation=capabilities.text_generation,
            image_understanding=capabilities.image_understanding,
            document_input=capabilities.document_input,
            tool_support=capabilities.tool_support,
            reasoning_support=capabilities.reasoning_support,
        )


class NumericParameterRangeResponse(BaseModel):
    minimum: float
    maximum: float
    default: float

    @classmethod
    def from_range(cls, value: NumericParameterRange) -> NumericParameterRangeResponse:
        return cls(minimum=value.minimum, maximum=value.maximum, default=value.default)


class ModelDefinitionResponse(BaseModel):
    identifier: str
    display_name: str
    capabilities: ModelCapabilitiesResponse
    context_size: int
    output_limit: int
    temperature: NumericParameterRangeResponse | None
    thinking_budget_minimum: int | None
    thinking_budget_maximum: int | None
    supported_parameters: list[str]
    availability_status: str

    @classmethod
    def from_model(cls, model: ModelDefinition) -> ModelDefinitionResponse:
        return cls(
            identifier=model.identifier,
            display_name=model.display_name,
            capabilities=ModelCapabilitiesResponse.from_capabilities(model.capabilities),
            context_size=model.context_size,
            output_limit=model.output_limit,
            temperature=(
                NumericParameterRangeResponse.from_range(model.temperature) if model.temperature is not None else None
            ),
            thinking_budget_minimum=model.thinking_budget_minimum,
            thinking_budget_maximum=model.thinking_budget_maximum,
            supported_parameters=list(model.supported_parameters),
            availability_status=model.availability_status,
        )


class ProviderDefinitionResponse(BaseModel):
    identifier: str
    display_name: str
    authentication_type: str
    adapter_available: bool
    health_status: str
    api_base_url: str
    capabilities: ModelCapabilitiesResponse
    models: list[ModelDefinitionResponse]

    @classmethod
    def from_provider(cls, provider: ProviderDefinition) -> ProviderDefinitionResponse:
        return cls(
            identifier=provider.identifier,
            display_name=provider.display_name,
            authentication_type=provider.authentication_type,
            adapter_available=provider.adapter_available,
            health_status=provider.health_status,
            api_base_url=provider.api_base_url,
            capabilities=ModelCapabilitiesResponse.from_capabilities(provider.capabilities),
            models=[ModelDefinitionResponse.from_model(model) for model in provider.models],
        )


class ProviderCatalogueResponse(BaseModel):
    providers: list[ProviderDefinitionResponse]


@provider_catalogue_router.get("/catalogue", response_model=ProviderCatalogueResponse)
async def get_catalogue(_: CurrentUser) -> ProviderCatalogueResponse:
    """Return the backend-owned provider and model capability catalogue."""
    catalogue = get_provider_catalogue()
    return ProviderCatalogueResponse(
        providers=[ProviderDefinitionResponse.from_provider(provider) for provider in catalogue.providers]
    )
