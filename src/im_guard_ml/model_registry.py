from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .dataio import load_yaml

REQUIRED_VERSION_FIELDS = [
    "model_version",
    "status",
    "prompt_version",
    "rubric_version",
    "feature_schema_version",
    "postprocess_version",
    "train_data_version",
    "eval_data_version",
]


def build_model_registry_report(path: str | Path = "configs/model_registry.yaml") -> dict[str, Any]:
    registry = load_yaml(path)
    models = registry.get("models", []) or []
    by_version = {str(item.get("model_version", "")): item for item in models if isinstance(item, dict)}
    checks: list[dict[str, Any]] = []

    _add(checks, "registry_has_models", "pass" if models else "fail", "Model registry contains at least one version.")

    current_stable = str(registry.get("current_stable", ""))
    candidate = str(registry.get("candidate", ""))
    _add(checks, "current_stable_exists", "pass" if current_stable in by_version else "fail", "current_stable points to a registered model.", detail={"current_stable": current_stable})
    _add(checks, "candidate_exists", "pass" if not candidate or candidate in by_version else "fail", "candidate points to a registered model or is empty.", detail={"candidate": candidate})

    versions_seen: set[str] = set()
    for model in models:
        if not isinstance(model, dict):
            _add(checks, "model_entry_object", "fail", "Every model registry entry must be an object.")
            continue
        version = str(model.get("model_version", ""))
        if version in versions_seen:
            _add(checks, f"unique_version:{version}", "fail", "Duplicate model_version in registry.")
        versions_seen.add(version)
        missing = [field for field in REQUIRED_VERSION_FIELDS if not str(model.get(field, "")).strip()]
        _add(
            checks,
            f"required_fields:{version or 'missing'}",
            "pass" if not missing else "fail",
            "Model version has required governance fields." if not missing else "Model version is missing required governance fields.",
            detail={"missing": missing},
        )
        status = str(model.get("status", ""))
        _add(
            checks,
            f"status_valid:{version or 'missing'}",
            "pass" if status in {"stable", "candidate", "retired"} else "fail",
            "Model status is valid.",
            detail={"status": status},
        )
        if status == "stable":
            _add(
                checks,
                f"stable_approved:{version}",
                "pass" if model.get("approved_by") and model.get("approved_at") else "fail",
                "Stable model has approval metadata.",
            )
        if status == "candidate":
            _add(
                checks,
                f"candidate_rollback:{version}",
                "pass" if model.get("rollback_to") in by_version else "fail",
                "Candidate model has a registered rollback target.",
                detail={"rollback_to": model.get("rollback_to", "")},
            )
        if status in {"stable", "candidate"}:
            for check in _metric_guardrail_checks(version, model.get("metrics", {}) or {}, registry.get("promotion_guardrails", {}) or {}):
                checks.append(check)

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warn_count = sum(1 for item in checks if item["status"] == "warn")
    return {
        "status": "fail" if fail_count else "warn" if warn_count else "pass",
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_path": str(path),
        "current_stable": current_stable,
        "candidate": candidate,
        "summary": {
            "pass": sum(1 for item in checks if item["status"] == "pass"),
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "checks": checks,
    }


def _metric_guardrail_checks(version: str, metrics: dict[str, Any], guardrails: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = [
        ("min_final_judgment_f1", "final_judgment_f1", ">="),
        ("min_handling_macro_f1", "handling_macro_f1", ">="),
        ("max_ban_account_fpr", "ban_account_fpr", "<="),
        ("max_parse_non_ok_rate", "parse_non_ok_rate", "<="),
        ("max_p95_latency_ms", "p95_latency_ms", "<="),
    ]
    checks: list[dict[str, Any]] = []
    for guardrail, metric, op in mapping:
        if guardrail not in guardrails:
            continue
        value = _as_float(metrics.get(metric))
        threshold = _as_float(guardrails.get(guardrail))
        if value is None or threshold is None:
            status = "fail"
        elif op == ">=":
            status = "pass" if value >= threshold else "fail"
        else:
            status = "pass" if value <= threshold else "fail"
        _add(
            checks,
            f"metric_guardrail:{version}:{metric}",
            status,
            f"{metric} satisfies {guardrail}." if status == "pass" else f"{metric} violates {guardrail}.",
            detail={"value": value, "threshold": threshold, "operator": op},
        )
    return checks


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _add(checks: list[dict[str, Any]], name: str, status: str, message: str, *, detail: dict[str, Any] | None = None) -> None:
    item: dict[str, Any] = {"name": name, "status": status, "message": message}
    if detail:
        item["detail"] = detail
    checks.append(item)
