from __future__ import annotations

from typing import Any

REQUIRED_ENDPOINTS = {
    "GET /health",
    "GET /ready",
    "GET /config",
    "POST /judge",
    "GET /dashboard/data",
    "GET /metrics",
    "GET /audit/tickets/{ticket_id}",
}


def build_openapi_contract(config_path: str = "configs/default.yaml") -> dict[str, Any]:
    from .api import create_app

    app = create_app(config_path)
    schema = app.openapi()
    schema["x-im-guard-required-endpoints"] = sorted(REQUIRED_ENDPOINTS)
    schema["x-im-guard-contract-status"] = validate_openapi_contract(schema)
    return schema


def validate_openapi_contract(schema: dict[str, Any]) -> dict[str, Any]:
    actual = _endpoint_set(schema)
    missing = sorted(REQUIRED_ENDPOINTS - actual)
    return {
        "status": "pass" if not missing else "fail",
        "missing": missing,
        "actual_count": len(actual),
        "required_count": len(REQUIRED_ENDPOINTS),
    }


def _endpoint_set(schema: dict[str, Any]) -> set[str]:
    endpoints: set[str] = set()
    for path, methods in schema.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method in methods:
            method_upper = method.upper()
            if method_upper in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                endpoints.add(f"{method_upper} {path}")
    return endpoints
