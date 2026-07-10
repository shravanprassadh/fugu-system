"""Provider-specific credential validation without persisting candidate secrets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from fugu.boot.config import get_settings
from fugu.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseMalformedError,
    ProviderTimeoutError,
    ProviderTransportError,
)

OPENROUTER_CREDENTIAL_TEST_URL = "https://openrouter.ai/api/v1/key"
NVIDIA_CREDENTIAL_TEST_URL = "https://integrate.api.nvidia.com/v1/models"
SUPPORTED_CREDENTIAL_PROVIDERS = frozenset({"openrouter", "nvidia"})


@dataclass(frozen=True, slots=True)
class CredentialValidationResult:
    """Sanitized outcome of one provider credential probe."""

    provider_name: str
    valid: bool
    message: str


def normalize_credential_provider(provider_name: str) -> str:
    """Normalize and validate one hosted provider identifier."""
    normalized = provider_name.strip().lower()
    if normalized not in SUPPORTED_CREDENTIAL_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_CREDENTIAL_PROVIDERS))
        raise ValueError(f"Unsupported provider {provider_name!r}. Supported providers: {supported}.")
    return normalized


def _credential_test_url(provider_name: str) -> str:
    return OPENROUTER_CREDENTIAL_TEST_URL if provider_name == "openrouter" else NVIDIA_CREDENTIAL_TEST_URL


def _raise_for_status(provider_name: str, status_code: int) -> None:
    label = "OpenRouter" if provider_name == "openrouter" else "NVIDIA"
    if status_code in {401, 403}:
        raise ProviderAuthenticationError(f"{label} rejected the provider credential.")
    if status_code == 429:
        raise ProviderRateLimitError(f"{label} rate limits prevented credential validation.")
    if status_code in {408, 504}:
        raise ProviderTimeoutError(f"{label} reported a credential-validation timeout.")
    if status_code < 200 or status_code >= 300:
        raise ProviderTransportError(
            f"{label} returned unsuccessful HTTP status {status_code} during credential validation."
        )


def _validate_response_shape(provider_name: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ProviderResponseMalformedError("The provider credential probe returned a non-object response.")
    data = payload.get("data")
    if provider_name == "openrouter" and not isinstance(data, dict):
        raise ProviderResponseMalformedError("OpenRouter returned malformed credential metadata.")
    if provider_name == "nvidia" and not isinstance(data, list):
        raise ProviderResponseMalformedError("NVIDIA returned a malformed model catalogue response.")


async def validate_provider_credential(
    provider_name: str,
    secret: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float | None = None,
) -> CredentialValidationResult:
    """Validate a candidate key using a read-only provider endpoint."""
    normalized = normalize_credential_provider(provider_name)
    candidate = secret.strip()
    if not candidate:
        raise ProviderAuthenticationError("Provider credentials cannot be empty.")

    if timeout_seconds is None:
        timeout_seconds = get_settings().network_request_timeout if client is None else 45.0
    if timeout_seconds <= 0:
        raise ValueError("Credential-validation timeouts must be positive.")

    owns_client = client is None
    resolved_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds))
    )
    try:
        try:
            response = await resolved_client.get(
                _credential_test_url(normalized),
                headers={"Authorization": f"Bearer {candidate}"},
            )
            _raise_for_status(normalized, response.status_code)
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderResponseMalformedError("The provider credential probe returned invalid JSON.") from exc
            _validate_response_shape(normalized, payload)
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The provider credential probe exceeded its configured timeout.") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError(
                "The provider credential probe failed before a response was received."
            ) from exc
    finally:
        if owns_client:
            await resolved_client.aclose()

    return CredentialValidationResult(
        provider_name=normalized,
        valid=True,
        message="Credential validation succeeded.",
    )
