"""Asynchronous NVIDIA NIM/OpenAI-compatible adapter with incremental SSE parsing."""

from __future__ import annotations

import json
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
from fugu.providers.openrouter import ServerSentEventParser

NVIDIA_CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


class NvidiaStreamProvider(ExecutionProvider):
    """Stream NVIDIA-hosted chat-completion output through a reusable async client."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        endpoint_url: str = NVIDIA_CHAT_COMPLETIONS_URL,
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
        """Send one non-blocking NVIDIA request and yield validated content fragments."""
        headers = {
            "Authorization": f"Bearer {request.credential_token}",
            "Content-Type": "application/json",
        }
        messages: list[dict[str, str]] = []
        if request.system_directives.strip():
            messages.append({"role": "system", "content": request.system_directives})
        messages.append({"role": "user", "content": request.prompt_content})
        payload: dict[str, object] = {
            "model": request.model_identifier,
            "stream": True,
            "messages": messages,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens

        client = self._get_client()
        parser = ServerSentEventParser()
        try:
            async with client.stream(
                "POST",
                self._endpoint_url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                self._raise_for_status(response.status_code)
                async for chunk in response.aiter_text():
                    for event_data in parser.feed(chunk):
                        if event_data.strip() == "[DONE]":
                            return
                        token = self._extract_token(event_data)
                        if token:
                            yield token

                for event_data in parser.finalize():
                    if event_data.strip() == "[DONE]":
                        return
                    token = self._extract_token(event_data)
                    if token:
                        yield token
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The NVIDIA request exceeded its configured timeout.") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError("The NVIDIA transport failed before the stream completed.") from exc

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code in {401, 403}:
            raise ProviderAuthenticationError("NVIDIA rejected the provider credential.")
        if status_code == 429:
            raise ProviderRateLimitError("NVIDIA rate limits were exceeded.")
        if status_code in {408, 504}:
            raise ProviderTimeoutError("NVIDIA reported a request timeout.")
        if status_code < 200 or status_code >= 300:
            raise ProviderTransportError(f"NVIDIA returned unsuccessful HTTP status {status_code}.")

    @classmethod
    def _extract_token(cls, event_data: str) -> str | None:
        try:
            payload = json.loads(event_data)
        except json.JSONDecodeError as exc:
            raise ProviderResponseMalformedError("NVIDIA emitted an invalid JSON SSE payload.") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseMalformedError("NVIDIA emitted a non-object JSON SSE payload.")

        error_payload = payload.get("error")
        if error_payload is not None:
            cls._raise_provider_error(error_payload)

        choices = payload.get("choices")
        if choices is None:
            return None
        if not isinstance(choices, list):
            raise ProviderResponseMalformedError("NVIDIA emitted a non-list choices payload.")
        if not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderResponseMalformedError("NVIDIA emitted a malformed choice object.")
        delta = first_choice.get("delta")
        if delta is None:
            return None
        if not isinstance(delta, dict):
            raise ProviderResponseMalformedError("NVIDIA emitted a malformed delta object.")
        content = delta.get("content")
        if content is None:
            return None
        if not isinstance(content, str):
            raise ProviderResponseMalformedError("NVIDIA emitted non-text token content.")
        return content or None

    @staticmethod
    def _raise_provider_error(error_payload: Any) -> None:
        if not isinstance(error_payload, dict):
            raise ProviderResponseMalformedError("NVIDIA emitted a malformed provider error object.")
        code = str(error_payload.get("code", ""))
        message = error_payload.get("message", "Provider request failed.")
        safe_message = message if isinstance(message, str) else "Provider request failed."
        if code in {"401", "403"}:
            raise ProviderAuthenticationError(safe_message)
        if code == "429":
            raise ProviderRateLimitError(safe_message)
        if code in {"408", "504"}:
            raise ProviderTimeoutError(safe_message)
        raise ProviderTransportError(safe_message)
