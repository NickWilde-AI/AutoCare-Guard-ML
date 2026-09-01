from __future__ import annotations

from collections import Counter
from typing import Any

from .schema import ServiceCase


def build_monitoring_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    predictions = [row.get("prediction", row) for row in rows]
    cases = rows
    report = {
        "total": len(rows),
        "prediction_distribution": {
            "risk_level": _field_dist(predictions, "risk_level"),
            "event_judgment": _field_dist(predictions, "event_judgment", fallback="final_judgment"),
            "recommended_action": _field_dist(
                predictions, "recommended_action", fallback="handling_suggestion"
            ),
            "route": _field_dist(predictions, "route"),
        },
        "input_distribution": {
            "conversation_evidence_count": _numeric_summary(
                [len(_conversation(row)) for row in cases]
            ),
            "fault_evidence_count": _numeric_summary(
                [len(row.get("fault_evidence") or []) for row in cases]
            ),
            "missing_vehicle_evidence": _numeric_summary(
                [0.0 if ServiceCase.from_dict(row).has_vehicle_side_evidence() else 1.0 for row in cases]
            ),
        },
        "quality_guards": _quality_guards(cases, predictions),
    }
    return report


def compare_reports(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_delta": current.get("total", 0) - baseline.get("total", 0),
        "risk_level_delta": _dist_delta(
            current.get("prediction_distribution", {}).get("risk_level", {}),
            baseline.get("prediction_distribution", {}).get("risk_level", {}),
        ),
        "action_delta": _dist_delta(
            current.get("prediction_distribution", {}).get("recommended_action", {}),
            baseline.get("prediction_distribution", {}).get("recommended_action", {}),
        ),
        "missing_vehicle_evidence_mean_delta": _mean_delta(
            current, baseline, "missing_vehicle_evidence"
        ),
    }


def build_sliding_window_report(
    rows: list[dict[str, Any]],
    *,
    window_size: int = 100,
    step_size: int | None = None,
    baseline_report: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate monitoring alerts across consecutive replay windows."""
    from .alerting import evaluate_alerts

    if window_size <= 0:
        raise ValueError("window_size must be positive")
    step = step_size if step_size is not None else window_size
    if step <= 0:
        raise ValueError("step_size must be positive")

    baseline = baseline_report or build_monitoring_report(rows)
    windows: list[dict[str, Any]] = []
    for start in range(0, max(len(rows), 1), step):
        window_rows = rows[start : start + window_size]
        if not window_rows:
            break
        report = build_monitoring_report(window_rows)
        diff = compare_reports(report, baseline)
        alert_result = evaluate_alerts({"current": report, "diff": diff}, thresholds)
        windows.append(
            {
                "window_index": len(windows),
                "start_index": start,
                "end_index": start + len(window_rows) - 1,
                "count": len(window_rows),
                "status": alert_result["status"],
                "alert_count": alert_result["alert_count"],
                "alerts": alert_result["alerts"],
                "quality_guards": report["quality_guards"],
            }
        )
        if start + window_size >= len(rows):
            break

    status = "pass"
    if any(window["status"] == "critical" for window in windows):
        status = "critical"
    elif any(window["status"] == "warn" for window in windows):
        status = "warn"
    return {
        "status": status,
        "total": len(rows),
        "window_size": window_size,
        "step_size": step,
        "window_count": len(windows),
        "windows": windows,
    }


def _field_dist(
    rows: list[dict[str, Any]], field: str, *, fallback: str | None = None
) -> dict[str, float]:
    values: list[str] = []
    for row in rows:
        value = row.get(field)
        if value is None and fallback:
            value = row.get(fallback)
        values.append(str(value if value is not None else "missing"))
    counter = Counter(values)
    total = sum(counter.values()) or 1
    return {k: v / total for k, v in sorted(counter.items())}


def _numeric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0}
    values = sorted(float(v) for v in values)
    from .evaluation import percentile

    return {
        "count": len(values),
        "min": values[0],
        "p50": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
        "max": values[-1],
        "mean": sum(values) / len(values),
    }


def _conversation(row: dict[str, Any]) -> list[Any]:
    value = row.get("conversation_evidence") or row.get("chat_evidence_list") or []
    return value if isinstance(value, list) else []


def _action(pred: dict[str, Any]) -> str:
    return str(pred.get("recommended_action") or pred.get("handling_suggestion") or "")


def _quality_guards(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases) or 1
    emergency_count = sum(1 for pred in predictions if _action(pred) == "emergency_review")
    parse_fail = sum(1 for pred in predictions if pred.get("parse_status") not in (None, "ok"))
    missing_vehicle = sum(
        1 for row in cases if not ServiceCase.from_dict(row).has_vehicle_side_evidence()
    )
    return {
        "emergency_review_rate": emergency_count / total,
        "parse_non_ok_rate": parse_fail / total,
        "missing_vehicle_evidence_rate": missing_vehicle / total,
    }


def _dist_delta(current: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    keys = sorted(set(current) | set(baseline))
    return {key: current.get(key, 0.0) - baseline.get(key, 0.0) for key in keys}


def _mean_delta(current: dict[str, Any], baseline: dict[str, Any], field: str) -> float:
    cur = current.get("input_distribution", {}).get(field, {}).get("mean", 0.0)
    base = baseline.get("input_distribution", {}).get(field, {}).get("mean", 0.0)
    return cur - base
