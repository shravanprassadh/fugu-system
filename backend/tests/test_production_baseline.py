from __future__ import annotations

import httpx
import pytest

from fugu.baseline import load_recorded_baseline
from fugu.production_baseline import ProductionBaselineError, verify_production_deployment


def _openapi_document() -> dict[str, object]:
    api = load_recorded_baseline()["api"]
    paths: dict[str, dict[str, object]] = {}
    for operation in api["operations"]:
        paths.setdefault(operation["path"], {})[operation["method"].lower()] = {
            "operationId": f"baseline_{operation['method'].lower()}_{len(paths)}"
        }
    return {
        "info": {"title": api["title"], "version": api["version"]},
        "paths": paths,
    }


def _transport(*, ready: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "frontend.example" and request.url.path == "/":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>Fugu</html>")
        if request.url.path == "/api/health/live":
            return httpx.Response(200, json={"status": "alive"})
        if request.url.path == "/api/health/ready":
            connections = {
                "master": "connected",
                "metadata": "connected",
                "logs": "connected" if ready else "unavailable",
            }
            return httpx.Response(
                200 if ready else 503,
                json={
                    "status": "ready" if ready else "unavailable",
                    "connections": connections,
                },
            )
        if request.url.path == "/api/openapi.json":
            return httpx.Response(200, json=_openapi_document())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_production_baseline_accepts_matching_stack() -> None:
    report = verify_production_deployment(
        frontend_url="https://frontend.example",
        backend_url="https://backend.example",
        transport=_transport(),
    )

    assert report["frontend"]["status"] == "reachable"
    assert report["backend"]["api_contract"] == "matched"
    assert report["backend"]["connections"]["logs"] == "connected"


def test_production_baseline_rejects_unready_database_pool() -> None:
    with pytest.raises(ProductionBaselineError, match="Production verification failed"):
        verify_production_deployment(
            frontend_url="https://frontend.example",
            backend_url="https://backend.example",
            transport=_transport(ready=False),
        )
