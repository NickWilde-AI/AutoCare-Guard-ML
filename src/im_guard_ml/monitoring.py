from __future__ import annotations

from collections import Counter
from typing import Any


def build_monitoring_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    predictions = [row.get("prediction", row) for row in rows]
    cases = rows
    report = {
        "total": len(rows),
        "prediction_distribution": {
            "risk_level": _field_dist(predictions, "risk_level"),
            "final_judgment": _field_dist(predictions, "final_judgment"),
            "handling_suggestion": _field_dist(predictions, "handling_suggestion"),
            "route": _field_dist(predictions, "route"),
        },
        "input_distribution": {
            "chat_evidence_count": _numeric_summary([len(row.get("chat_evidence_list", []) or []) for row in cases]),
            "behavior_abnormal_count": _numeric_summary([len(row.get("behavior_abnormal_list", []) or []) for row in cases]),
            "gift_total_value": _numeric_summary([_gift_value(row) for row in cases]),
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
        "handling_delta": _dist_delta(
            current.get("prediction_distribution", {}).get("handling_suggestion", {}),
            baseline.get("prediction_distribution", {}).get("handling_suggestion", {}),
        ),
        "gift_total_value_mean_delta": _mean_delta(current, baseline, "gift_total_value"),
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
        window_rows = rows[start:start + window_size]
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


def _field_dist(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    counter = Counter(str(row.get(field, "missing")) for row in rows)
    total = sum(counter.values()) or 1
    return {k: v / total for k, v in sorted(counter.items())}


def _numeric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0}
    values = sorted(float(v) for v in values)
    return {
        "count": len(values),
        "min": values[0],
        "p50": values[len(values) // 2],
        "p95": values[min(len(values) - 1, int(len(values) * 0.95))],
        "max": values[-1],
        "mean": sum(values) / len(values),
    }


def _gift_value(row: dict[str, Any]) -> float:
    summary = row.get("audit_scene", {}).get("behavior_key_summary", {})
    try:
        return float(summary.get("gift_total_value", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _quality_guards(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases) or 1
    ban_count = sum(1 for pred in predictions if pred.get("handling_suggestion") == "ban_account")
    parse_fail = sum(1 for pred in predictions if pred.get("parse_status") not in (None, "ok"))
    empty_behavior = sum(1 for row in cases if not row.get("behavior_abnormal_list") and not row.get("audit_scene", {}).get("behavior_key_summary"))
    return {
        "ban_account_rate": ban_count / total,
        "parse_non_ok_rate": parse_fail / total,
        "empty_behavior_rate": empty_behavior / total,
    }


def _dist_delta(current: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    keys = sorted(set(current) | set(baseline))
    return {key: current.get(key, 0.0) - baseline.get(key, 0.0) for key in keys}


def _mean_delta(current: dict[str, Any], baseline: dict[str, Any], field: str) -> float:
    cur = current.get("input_distribution", {}).get(field, {}).get("mean", 0.0)
    base = baseline.get("input_distribution", {}).get(field, {}).get("mean", 0.0)
    return cur - base
