"""FastAPI application entry point for the modular Fugu backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fugu.api.routes import auth_router, execution_router
from fugu.database.connection import get_session_registry
from fugu.execution.kernel import get_execution_kernel


@asynccontextmanager
async def application_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Dispose lazily created database pools during application shutdown."""
    yield
    get_execution_kernel.cache_clear()
    if get_session_registry.cache_info().currsize:
        registry = get_session_registry()
        await registry.dispose_pools()
        get_session_registry.cache_clear()


def create_app() -> FastAPI:
    """Construct the Fugu API without initializing external resources at import time."""
    application = FastAPI(
        title="Fugu Modular Kernel API",
        version="0.1.0",
        lifespan=application_lifespan,
    )
    application.include_router(auth_router)
    application.include_router(execution_router)
    return application


app = create_app()
