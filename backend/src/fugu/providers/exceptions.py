"""Typed failures for model-provider registration and transport operations."""


class ProviderError(RuntimeError):
    """Base error for all provider-layer failures."""


class ProviderRegistryError(ProviderError):
    """Base error for provider registration and resolution failures."""


class ProviderNotRegisteredError(ProviderRegistryError):
    """Raised when no provider factory is registered for a normalized name."""


class ProviderAlreadyRegisteredError(ProviderRegistryError):
    """Raised when a provider name is registered twice without replacement."""


class ProviderAuthenticationError(ProviderError):
    """Raised when a provider rejects the supplied credential."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider rejects a request because of usage limits."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds a configured timeout."""


class ProviderTransportError(ProviderError):
    """Raised when a provider cannot be reached or returns an unsuccessful response."""


class ProviderResponseMalformedError(ProviderError):
    """Raised when a provider stream contains malformed SSE or JSON data."""
