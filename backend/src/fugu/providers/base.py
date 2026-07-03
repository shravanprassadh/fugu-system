"""Strict asynchronous contract shared by every model provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Immutable input required to execute one provider streaming request."""

    prompt_content: str
    system_directives: str
    credential_token: str
    model_identifier: str

    def __post_init__(self) -> None:
        if not self.prompt_content.strip():
            raise ValueError("Provider prompts cannot be empty.")
        if not self.credential_token.strip():
            raise ValueError("Provider credentials cannot be empty.")
        if not self.model_identifier.strip():
            raise ValueError("Provider model identifiers cannot be empty.")


class ExecutionProvider(ABC):
    """Interface implemented by every asynchronous token-streaming provider."""

    @abstractmethod
    def generate_token_stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """Yield model output fragments without blocking the event loop."""

    async def aclose(self) -> None:
        """Release provider-owned network resources when applicable."""
