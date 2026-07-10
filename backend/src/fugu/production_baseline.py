"""Non-secret verification of a deployed Fugu frontend and backend."""

from __future__ import annotations

from typing import Any

import httpx

from fugu.baseline import load_recorded_baseline

_HTTP_METHODS = frozenset({"delete", "get", "patch", "post", "put"})
_EXPECTED_CONNECTIONS = {"master": "connected", "metadata": "connected", "logs": "connected"}


class ProductionBaselineError(RuntimeError):
    """Raised when the deployed stack does not satisfy the baseline contract."""


def _request_json(client: httpx.Client, url: str) -> dict[str, Any]:
    try:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProductionBaselineError(f"Production verification failed for {url}.") from exc
    if not isinstance(payload, dict):
        raise ProductionBaselineError(f"Production endpoint {url} did not return a JSON object.")
    return payload


def _openapi_operations(schema: dict[str, Any]) -> list[dict[str, str]]:
    raw_paths = schema.get("paths")
    if not isinstance(raw_paths, dict):
        raise ProductionBaselineError("The deployed OpenAPI document has no paths object.")

    operations: list[dict[str, str]] = []
    for path, path_item in raw_paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method in path_item:
            if isinstance(method, str) and method.lower() in _HTTP_METHODS:
                operations.append({"method": method.upper(), "path": path})
    operations.sort(key=lambda item: (item["path"], item["method"]))
    return operations


def verify_production_deployment(
    *,
    frontend_url: str,
    backend_url: str,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Verify public reachability, database readiness, and deployed API compatibility."""
    normalized_frontend = frontend_url.rstrip("/")
    normalized_backend = backend_url.rstrip("/")
    if not normalized_frontend.startswith("https://") or not normalized_backend.startswith("https://"):
        raise ProductionBaselineError("Production frontend and backend URLs must use HTTPS.")

    timeout = httpx.Timeout(30.0, connect=15.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, transport=transport) as client:
        try:
            frontend_response = client.get(f"{normalized_frontend}/")
            frontend_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProductionBaselineError("The production frontend is not reachable.") from exc
        content_type = frontend_response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            raise ProductionBaselineError("The production frontend did not return HTML.")

        live = _request_json(client, f"{normalized_backend}/api/health/live")
        if live.get("status") != "alive":
            raise ProductionBaselineError("The backend liveness endpoint is not alive.")

        ready = _request_json(client, f"{normalized_backend}/api/health/ready")
        if ready.get("status") != "ready" or ready.get("connections") != _EXPECTED_CONNECTIONS:
            raise ProductionBaselineError(
                "The backend readiness endpoint did not confirm master, metadata, and logs connectivity."
            )

        openapi = _request_json(client, f"{normalized_backend}/api/openapi.json")

    recorded = load_recorded_baseline()["api"]
    deployed_api = {
        "title": (
            openapi.get("info", {}).get("title")
            if isinstance(openapi.get("info"), dict)
            else None
        ),
        "version": (
            openapi.get("info", {}).get("version")
            if isinstance(openapi.get("info"), dict)
            else None
        ),
        "operations": _openapi_operations(openapi),
    }
    if deployed_api != recorded:
        raise ProductionBaselineError(
            "The deployed OpenAPI contract does not match docs/baseline/system-contract.json."
        )

    return {
        "frontend": {"url": normalized_frontend, "status": "reachable"},
        "backend": {
            "url": normalized_backend,
            "liveness": "alive",
            "readiness": "ready",
            "connections": dict(_EXPECTED_CONNECTIONS),
            "api_contract": "matched",
        },
    }
