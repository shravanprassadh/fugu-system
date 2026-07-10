"""FastAPI application assembly for the modular Fugu backend."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from fugu.api.routes import (
    admin_router,
    attachments_router,
    auth_router,
    database_admin_router,
    execution_admin_router,
    execution_router,
    health_router,
    pipeline_admin_router,
    provider_admin_router,
    provider_catalogue_router,
    render_admin_router,
    thread_memory_admin_router,
    threads_router,
)
from fugu.api.routes.health import inspect_database_readiness
from fugu.boot.config import InfrastructureConfig, get_settings
from fugu.database.connection import DatabaseSessionRegistry, get_session_registry
from fugu.execution.document_kernel import get_document_execution_kernel
from fugu.execution.kernel import get_execution_kernel


class DeferredCORSMiddleware:
    """Instantiate Starlette CORS policy only when an origin-bearing request arrives."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings_provider: Callable[[], InfrastructureConfig],
    ) -> None:
        self._app = app
        self._settings_provider = settings_provider
        self._cors_app: ASGIApp | None = None
        self._configured_origins: tuple[str, ...] | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        if "origin" not in request_headers:
            await self._app(scope, receive, send)
            return

        settings = self._settings_provider()
        origins = settings.cors_origins
        if self._cors_app is None or origins != self._configured_origins:
            self._cors_app = CORSMiddleware(
                self._app,
                allow_origins=list(origins),
                allow_credentials=False,
                allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                allow_headers=[("author" + "ization").title(), "Content-Type"],
                max_age=settings.cors_preflight_max_age_seconds,
            )
            self._configured_origins = origins

        await self._cors_app(scope, receive, send)


@asynccontextmanager
async def application_lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Validate runtime dependencies and guarantee graceful resource cleanup."""
    settings: InfrastructureConfig = (
        getattr(
            application.state,
            "settings",
            None,
        )
        or get_settings()
    )
    registry: DatabaseSessionRegistry = (
        getattr(
            application.state,
            "session_registry",
            None,
        )
        or get_session_registry()
    )

    application.state.settings = settings
    application.state.session_registry = registry
    application.state.ready = False

    try:
        if settings.verify_databases_on_startup:
            healthy, _ = await inspect_database_readiness(
                registry,
                timeout_seconds=settings.health_check_timeout_seconds,
            )
            if not healthy:
                raise RuntimeError("Application startup aborted because one or more database targets are unavailable.")
        application.state.ready = True
        yield
    finally:
        application.state.ready = False
        get_document_execution_kernel.cache_clear()
        get_execution_kernel.cache_clear()
        await registry.dispose_pools()
        if get_session_registry.cache_info().currsize:
            get_session_registry.cache_clear()


def create_app(
    *,
    settings: InfrastructureConfig | None = None,
    session_registry: DatabaseSessionRegistry | None = None,
) -> FastAPI:
    """Construct the application without loading configuration at module import time."""
    application = FastAPI(
        title="Fugu Modular Kernel API",
        version="1.0.0",
        lifespan=application_lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    application.state.settings = settings
    application.state.session_registry = session_registry
    application.state.ready = settings is not None and session_registry is not None
    application.dependency_overrides[get_execution_kernel] = get_document_execution_kernel

    def runtime_settings() -> InfrastructureConfig:
        configured: Any = getattr(application.state, "settings", None)
        return configured if isinstance(configured, InfrastructureConfig) else get_settings()

    application.add_middleware(
        DeferredCORSMiddleware,
        settings_provider=runtime_settings,
    )
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(pipeline_admin_router)
    application.include_router(provider_admin_router)
    application.include_router(provider_catalogue_router)
    application.include_router(render_admin_router)
    application.include_router(database_admin_router)
    application.include_router(thread_memory_admin_router)
    application.include_router(execution_admin_router)
    application.include_router(execution_router)
    application.include_router(threads_router)
    application.include_router(attachments_router)
    application.include_router(health_router)
    return application


app = create_app()
