"""API route modules."""

from fugu.api.routes.admin import admin_router
from fugu.api.routes.auth import auth_router
from fugu.api.routes.database_admin import database_admin_router
from fugu.api.routes.execution import execution_router
from fugu.api.routes.health import health_router
from fugu.api.routes.provider_admin import provider_admin_router
from fugu.api.routes.render_admin import render_admin_router
from fugu.api.routes.threads import threads_router

__all__ = [
    "admin_router",
    "auth_router",
    "database_admin_router",
    "execution_router",
    "health_router",
    "provider_admin_router",
    "render_admin_router",
    "threads_router",
]
