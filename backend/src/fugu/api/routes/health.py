"""Liveness and deep readiness endpoints for production orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Protocol

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fugu.database.connection import DatabaseTarget

health_router = APIRouter(prefix="/api/health", tags=["system diagnostics"])


class ReadinessRegistry(Protocol):
    """Minimal database-registry contract required by readiness probes."""

    async def ping(self, target: DatabaseTarget | str = DatabaseTarget.MASTER) -> None:
        """Raise when the selected target is unavailable."""


class LivenessResponse(BaseModel):
    """Static process-liveness response."""

    status: str


class ReadinessResponse(BaseModel):
    """Sanitized multi-pool readiness response."""

    status: str
    connections: dict[str, str]


async def inspect_database_readiness(
    registry: ReadinessRegistry,
    *,
    timeout_seconds: float,
) -> tuple[bool, Mapping[str, str]]:
    """Probe every configured workload pool concurrently without leaking errors."""

    async def inspect_target(target: DatabaseTarget) -> tuple[str, str]:
        try:
            async with asyncio.timeout(timeout_seconds):
                await registry.ping(target)
        except Exception:
            return target.value, "unavailable"
        return target.value, "connected"

    results = await asyncio.gather(*(inspect_target(target) for target in DatabaseTarget))
    connections = dict(results)
    return all(value == "connected" for value in connections.values()), connections


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@health_router.get("/live", response_model=LivenessResponse)
async def liveness_probe(response: Response) -> LivenessResponse:
    """Confirm that the process and event loop can serve requests."""
    _no_store(response)
    return LivenessResponse(status="alive")


@health_router.get("/ready", response_model=ReadinessResponse)
@health_router.get("", response_model=ReadinessResponse, include_in_schema=False)
async def readiness_probe(request: Request) -> ReadinessResponse | JSONResponse:
    """Verify startup state and active connectivity across all database pools."""
    settings = request.app.state.settings
    registry: ReadinessRegistry = request.app.state.session_registry
    application_ready = bool(getattr(request.app.state, "ready", False))
    healthy, connections = await inspect_database_readiness(
        registry,
        timeout_seconds=settings.health_check_timeout_seconds,
    )
    payload = ReadinessResponse(
        status="ready" if application_ready and healthy else "unavailable",
        connections=dict(connections),
    )
    if not application_ready or not healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=payload.model_dump(),
        headers={"Cache-Control": "no-store"},
    )
