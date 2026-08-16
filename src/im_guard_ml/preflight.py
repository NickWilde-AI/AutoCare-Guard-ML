from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PLACEHOLDER_HASH = "0" * 64


def build_production_preflight(env_file: str | Path | None = None, *, environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(environ if environ is not None else os.environ)
    if env_file:
        env.update(_read_env_file(env_file))

    checks: list[dict[str, Any]] = []

    auth_values = [
        env.get("IM_GUARD_API_TOKEN", "").strip(),
        env.get("IM_GUARD_API_TOKENS", "").strip(),
        env.get("IM_GUARD_API_TOKEN_HASHES", "").strip(),
    ]
    _add(
        checks,
        "api_auth_enabled",
        "pass" if any(auth_values) else "fail",
        "API auth is configured." if any(auth_values) else "Production API must configure IM_GUARD_API_TOKEN_HASHES or another token source.",
    )
    token_hashes = _parse_token_hashes(env.get("IM_GUARD_API_TOKEN_HASHES", ""))
    if token_hashes:
        invalid = [item for item in token_hashes if not _is_sha256_hex(item["hash"])]
        placeholders = [item for item in token_hashes if item["hash"] == PLACEHOLDER_HASH]
        _add(
            checks,
            "api_token_hash_format",
            "fail" if invalid else "pass",
            "All configured token hashes are valid SHA-256 hex strings." if not invalid else "Invalid SHA-256 token hashes detected.",
            detail={"invalid_count": len(invalid)},
        )
        if placeholders:
            _add(checks, "api_token_hash_placeholder", "warn", "Replace placeholder token hashes before real deployment.")
    elif env.get("IM_GUARD_API_TOKEN", "") or env.get("IM_GUARD_API_TOKENS", ""):
        _add(checks, "api_plaintext_token", "warn", "Plaintext tokens are acceptable for demo, but production should prefer IM_GUARD_API_TOKEN_HASHES.")

    cors = _split_csv(env.get("IM_GUARD_CORS_ORIGINS", "*"))
    _add(
        checks,
        "cors_not_wildcard",
        "pass" if cors and "*" not in cors else "fail",
        "CORS origins are restricted." if cors and "*" not in cors else "Production CORS must not be wildcard '*'.",
        detail={"origins": cors},
    )

    backend = env.get("IM_GUARD_AUDIT_BACKEND", "jsonl").strip().lower()
    _add(
        checks,
        "audit_backend_supported",
        "pass" if backend in {"jsonl", "sqlite"} else "fail",
        "Audit backend is supported." if backend in {"jsonl", "sqlite"} else "Unsupported audit backend.",
        detail={"backend": backend},
    )
    _add(
        checks,
        "audit_backend_production_ready",
        "pass" if backend == "sqlite" else "warn",
        "SQLite audit backend is enabled for production-like single service deployment." if backend == "sqlite" else "JSONL audit backend is demo-oriented; prefer SQLite for production-like showcase.",
    )
    audit_path = env.get("IM_GUARD_AUDIT_LOG_PATH", "").strip()
    _add(
        checks,
        "audit_log_path_configured",
        "pass" if audit_path else "fail",
        "Audit log path is configured." if audit_path else "Production deployment must configure IM_GUARD_AUDIT_LOG_PATH.",
        detail={"path": audit_path},
    )

    max_bytes = _parse_int(env.get("IM_GUARD_MAX_REQUEST_BYTES", ""), default=0)
    _add(
        checks,
        "max_request_bytes_positive",
        "pass" if max_bytes > 0 else "fail",
        "Request size limit is enabled." if max_bytes > 0 else "Production deployment must enable request size limit.",
        detail={"max_request_bytes": max_bytes},
    )
    rate_limit = _parse_int(env.get("IM_GUARD_RATE_LIMIT_PER_MINUTE", ""), default=-1)
    _add(
        checks,
        "rate_limit_enabled",
        "pass" if rate_limit > 0 else "fail",
        "Per-IP rate limit is enabled." if rate_limit > 0 else "Production deployment must enable rate limiting.",
        detail={"rate_limit_per_minute": rate_limit},
    )

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warn_count = sum(1 for item in checks if item["status"] == "warn")
    return {
        "status": "fail" if fail_count else "warn" if warn_count else "pass",
        "generated_at": datetime.now(UTC).isoformat(),
        "env_file": str(env_file) if env_file else None,
        "summary": {
            "pass": sum(1 for item in checks if item["status"] == "pass"),
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "checks": checks,
    }


def _read_env_file(path: str | Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _parse_token_hashes(value: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in _split_csv(value):
        token_hash, role = raw.split(":", 1) if ":" in raw else (raw, "admin")
        items.append({"hash": token_hash.strip().lower(), "role": role.strip() or "admin"})
    return items


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_int(value: str, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _add(checks: list[dict[str, Any]], name: str, status: str, message: str, *, detail: dict[str, Any] | None = None) -> None:
    item: dict[str, Any] = {"name": name, "status": status, "message": message}
    if detail:
        item["detail"] = detail
    checks.append(item)
