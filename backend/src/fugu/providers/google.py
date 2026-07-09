"""Asynchronous Google Gemini adapter for non-streaming utility model calls."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from fugu.boot.config import get_settings
from fugu.providers.base import ExecutionProvider, ProviderRequest
from fugu.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseMalformedError,
    ProviderTimeoutError,
    ProviderTransportError,
)

GOOGLE_GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class GoogleGeminiProvider(ExecutionProvider):
    """Call Google Gemini through the Interactions REST API and yield one text chunk."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        endpoint_url: str = GOOGLE_GEMINI_INTERACTIONS_URL,
        timeout_seconds: float | None = None,
    ) -> None:
        if timeout_seconds is None:
            timeout_seconds = get_settings().network_request_timeout if client is None else 45.0
        if timeout_seconds <= 0:
            raise ValueError("Provider timeouts must be positive.")
        self._client = client
        self._owns_client = client is None
        self._endpoint_url = endpoint_url
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds))

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """Close only a client created and owned by this provider instance."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def generate_token_stream(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[str]:
        """Send one Gemini Interactions request and yield the returned text once."""
        payload: dict[str, Any] = {
            "model": request.model_identifier,
            "input": request.prompt_content,
            "generation_config": {
                "temperature": 0.2,
                "thinking_level": "low",
            },
        }
        if request.system_directives.strip():
            payload["system_instruction"] = request.system_directives

        client = self._get_client()
        try:
            response = await client.post(
                self._endpoint_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": request.credential_token,
                },
                timeout=self._timeout,
            )
            self._raise_for_status(response.status_code, response)
            text = self._extract_output_text(response.json())
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The Google Gemini request exceeded its configured timeout.") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError("The Google Gemini transport failed before the request completed.") from exc
        except ValueError as exc:
            raise ProviderResponseMalformedError("Google Gemini returned a non-JSON response.") from exc

        if text:
            yield text

    @staticmethod
    def _raise_for_status(status_code: int, response: httpx.Response) -> None:
        if 200 <= status_code < 300:
            return
        message = GoogleGeminiProvider._safe_error_message(response)
        if status_code in {401, 403}:
            raise ProviderAuthenticationError(message or "Google Gemini rejected the provider credential.")
        if status_code == 429:
            raise ProviderRateLimitError(message or "Google Gemini rate limits were exceeded.")
        if status_code in {408, 504}:
            raise ProviderTimeoutError(message or "Google Gemini reported a request timeout.")
        raise ProviderTransportError(message or f"Google Gemini returned unsuccessful HTTP status {status_code}.")

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        if not isinstance(payload, dict):
            return ""
        error_payload = payload.get("error")
        if not isinstance(error_payload, dict):
            return ""
        message = error_payload.get("message")
        return message if isinstance(message, str) else ""

    @staticmethod
    def _extract_output_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            raise ProviderResponseMalformedError("Google Gemini returned a non-object JSON payload.")
        output_text = payload.get("output_text")
        if isinstance(output_text, str):
            return output_text

        text_blocks: list[str] = []
        for step in payload.get("steps", []):
            if not isinstance(step, dict):
                continue
            for part in step.get("output", []) or step.get("content", []) or []:
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                    text_blocks.append(part["text"])
        if text_blocks:
            return "".join(text_blocks)
        raise ProviderResponseMalformedError("Google Gemini response did not contain output_text.")
