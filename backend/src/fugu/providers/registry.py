"""Thread-safe provider factory registration and resolution."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from threading import RLock

from fugu.providers.base import ExecutionProvider
from fugu.providers.exceptions import (
    ProviderAlreadyRegisteredError,
    ProviderNotRegisteredError,
)

ProviderFactory = Callable[[], ExecutionProvider]


class ProviderRegistry:
    """Map normalized provider names to factories without global mutable state."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}
        self._lock = RLock()

    @staticmethod
    def normalize_name(provider_name: str) -> str:
        """Normalize a provider identifier and reject blank names."""
        normalized = provider_name.strip().lower()
        if not normalized:
            raise ValueError("Provider names cannot be empty.")
        return normalized

    def register(
        self,
        provider_name: str,
        factory: ProviderFactory,
        *,
        replace: bool = False,
    ) -> None:
        """Register a provider factory with explicit duplicate behavior."""
        normalized = self.normalize_name(provider_name)
        with self._lock:
            if normalized in self._factories and not replace:
                raise ProviderAlreadyRegisteredError(f"Provider {normalized!r} is already registered.")
            self._factories[normalized] = factory

    def resolve(self, provider_name: str) -> ExecutionProvider:
        """Instantiate the provider registered under a normalized name."""
        normalized = self.normalize_name(provider_name)
        with self._lock:
            factory = self._factories.get(normalized)
        if factory is None:
            raise ProviderNotRegisteredError(f"Provider {normalized!r} is not registered.")
        return factory()

    def registered_names(self) -> tuple[str, ...]:
        """Return a deterministic snapshot of registered provider names."""
        with self._lock:
            return tuple(sorted(self._factories))


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    """Build the application registry lazily to avoid import-time clients or settings."""
    from fugu.providers.nvidia import NvidiaStreamProvider
    from fugu.providers.openrouter import OpenRouterStreamProvider

    registry = ProviderRegistry()
    registry.register("nvidia", NvidiaStreamProvider)
    registry.register("openrouter", OpenRouterStreamProvider)
    return registry
