"""Asynchronous relational data tier for Fugu.

Public database symbols are resolved lazily so importing a lightweight
submodule such as ``fugu.database.urls`` does not initialize connection pools
or re-enter boot configuration during module import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fugu.database.connection import (
        DatabaseSessionRegistry,
        DatabaseTarget,
        get_session_registry,
    )
    from fugu.database.models import Base

__all__ = ["Base", "DatabaseSessionRegistry", "DatabaseTarget", "get_session_registry"]


def __getattr__(name: str) -> Any:
    """Resolve public database exports without eager package side effects."""
    if name == "Base":
        from fugu.database.models import Base

        return Base

    if name in {"DatabaseSessionRegistry", "DatabaseTarget", "get_session_registry"}:
        from fugu.database.connection import (
            DatabaseSessionRegistry,
            DatabaseTarget,
            get_session_registry,
        )

        exports = {
            "DatabaseSessionRegistry": DatabaseSessionRegistry,
            "DatabaseTarget": DatabaseTarget,
            "get_session_registry": get_session_registry,
        }
        return exports[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose lazy public attributes to introspection tools."""
    return sorted(set(globals()) | set(__all__))
