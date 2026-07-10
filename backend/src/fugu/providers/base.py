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
    temperature: float | None = None
    max_output_tokens: int | None = None
    thinking_budget: int | None = None

    def __post_init__(self) -> None:
        if not self.prompt_content.strip():
            raise ValueError("Provider prompts cannot be empty.")
        if not self.credential_token.strip():
            raise ValueError("Provider credentials cannot be empty.")
        if not self.model_identifier.strip():
            raise ValueError("Provider model identifiers cannot be empty.")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("Provider output limits must be positive.")
        if self.thinking_budget is not None and self.thinking_budget < 1:
            raise ValueError("Provider thinking budgets must be positive.")


class ExecutionProvider(ABC):
    """Interface implemented by every asynchronous token-streaming provider."""

    @abstractmethod
    def generate_token_stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """Yield model output fragments without blocking the event loop."""

    async def aclose(self) -> None:
        """Release provider-owned network resources when applicable."""
