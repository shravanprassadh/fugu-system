"""Asynchronous OpenRouter adapter with incremental SSE parsing."""

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

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class ServerSentEventParser:
    """Incrementally reconstruct SSE data events across arbitrary text chunks."""

    def __init__(self) -> None:
        self._buffer = ""
        self._data_lines: list[str] = []

    def feed(self, chunk: str) -> list[str]:
        """Consume a text chunk and return every complete SSE data event."""
        self._buffer += chunk
        events: list[str] = []
        while "\n" in self._buffer:
            raw_line, self._buffer = self._buffer.split("\n", 1)
            line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
            event = self._consume_line(line)
            if event is not None:
                events.append(event)
        return events

    def finalize(self) -> list[str]:
        """Flush a final unterminated line and pending event at end-of-stream."""
        events: list[str] = []
        if self._buffer:
            line = self._buffer[:-1] if self._buffer.endswith("\r") else self._buffer
            self._buffer = ""
            event = self._consume_line(line)
            if event is not None:
                events.append(event)
        pending = self._dispatch()
        if pending is not None:
            events.append(pending)
        return events

    def _consume_line(self, line: str) -> str | None:
        if not line:
            return self._dispatch()
        if line.startswith(":"):
            return None

        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data_lines.append(value)
        return None

    def _dispatch(self) -> str | None:
        if not self._data_lines:
            return None
        event = "\n".join(self._data_lines)
        self._data_lines.clear()
        return event


class OpenRouterStreamProvider(ExecutionProvider):
    """Stream OpenRouter chat-completion output through a reusable async client."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        endpoint_url: str = OPENROUTER_CHAT_COMPLETIONS_URL,
        timeout_seconds: float | None = None,
    ) -> None:
        if timeout_seconds is None:
            timeout_seconds = (
                get_settings().network_request_timeout if client is None else 45.0
            )
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
        """Send one non-blocking request and yield validated content fragments."""
        headers = {
            "Authorization": f"Bearer {request.credential_token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/shravanprassadh/fugu-system",
            "X-Title": "Fugu Modular Kernel",
        }
        messages: list[dict[str, str]] = []
        if request.system_directives.strip():
            messages.append(
                {"role": "system", "content": request.system_directives}
            )
        messages.append({"role": "user", "content": request.prompt_content})
        payload = {
            "model": request.model_identifier,
            "stream": True,
            "messages": messages,
        }

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
            raise ProviderTimeoutError(
                "The OpenRouter request exceeded its configured timeout."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderTransportError(
                "The OpenRouter transport failed before the stream completed."
            ) from exc

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "OpenRouter rejected the provider credential."
            )
        if status_code == 429:
            raise ProviderRateLimitError("OpenRouter rate limits were exceeded.")
        if status_code in {408, 504}:
            raise ProviderTimeoutError("OpenRouter reported a request timeout.")
        if status_code < 200 or status_code >= 300:
            raise ProviderTransportError(
                f"OpenRouter returned unsuccessful HTTP status {status_code}."
            )

    @classmethod
    def _extract_token(cls, event_data: str) -> str | None:
        try:
            payload = json.loads(event_data)
        except json.JSONDecodeError as exc:
            raise ProviderResponseMalformedError(
                "OpenRouter emitted an invalid JSON SSE payload."
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderResponseMalformedError(
                "OpenRouter emitted a non-object JSON SSE payload."
            )

        error_payload = payload.get("error")
        if error_payload is not None:
            cls._raise_provider_error(error_payload)

        choices = payload.get("choices")
        if choices is None:
            return None
        if not isinstance(choices, list):
            raise ProviderResponseMalformedError(
                "OpenRouter emitted a non-list choices payload."
            )
        if not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderResponseMalformedError(
                "OpenRouter emitted a malformed choice object."
            )
        delta = first_choice.get("delta")
        if delta is None:
            return None
        if not isinstance(delta, dict):
            raise ProviderResponseMalformedError(
                "OpenRouter emitted a malformed delta object."
            )
        content = delta.get("content")
        if content is None:
            return None
        if not isinstance(content, str):
            raise ProviderResponseMalformedError(
                "OpenRouter emitted non-text token content."
            )
        return content or None

    @staticmethod
    def _raise_provider_error(error_payload: Any) -> None:
        if not isinstance(error_payload, dict):
            raise ProviderResponseMalformedError(
                "OpenRouter emitted a malformed provider error object."
            )
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
