from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_THRESHOLDS = {
    "emergency_review_rate_warn": 0.05,
    "emergency_review_rate_critical": 0.08,
    "parse_non_ok_rate_warn": 0.005,
    "parse_non_ok_rate_critical": 0.02,
    "missing_vehicle_evidence_rate_warn": 0.08,
    "missing_vehicle_evidence_rate_critical": 0.20,
    "missing_vehicle_evidence_mean_delta_warn": 0.08,
    "missing_vehicle_evidence_mean_delta_critical": 0.20,
}


@dataclass(slots=True)
class Alert:
    name: str
    severity: str
    value: float
    threshold: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
        }


def evaluate_alerts(report: dict[str, Any], thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    current = report.get("current", report)
    diff = report.get("diff", {})
    guards = current.get("quality_guards", {})
    alerts: list[Alert] = []
    alerts.extend(
        _threshold_alert(
            "emergency_review_rate",
            float(guards.get("emergency_review_rate", 0.0)),
            thresholds["emergency_review_rate_warn"],
            thresholds["emergency_review_rate_critical"],
            "emergency_review 占比异常，需检查车辆证据门禁与高风险分布。",
        )
    )
    alerts.extend(
        _threshold_alert(
            "parse_non_ok_rate",
            float(guards.get("parse_non_ok_rate", 0.0)),
            thresholds["parse_non_ok_rate_warn"],
            thresholds["parse_non_ok_rate_critical"],
            "解析异常率升高，需检查模型输出格式、prompt 或后处理。",
        )
    )
    alerts.extend(
        _threshold_alert(
            "missing_vehicle_evidence_rate",
            float(guards.get("missing_vehicle_evidence_rate", 0.0)),
            thresholds["missing_vehicle_evidence_rate_warn"],
            thresholds["missing_vehicle_evidence_rate_critical"],
            "车辆侧证据缺失率升高，需检查信号/故障接入。",
        )
    )
    if diff:
        alerts.extend(
            _abs_delta_alert(
                "missing_vehicle_evidence_mean_delta",
                float(diff.get("missing_vehicle_evidence_mean_delta", 0.0)),
                thresholds["missing_vehicle_evidence_mean_delta_warn"],
                thresholds["missing_vehicle_evidence_mean_delta_critical"],
                "车辆证据缺失均值相对 baseline 漂移，需检查证据链路。",
            )
        )
    severity = "pass"
    if any(alert.severity == "critical" for alert in alerts):
        severity = "critical"
    elif alerts:
        severity = "warn"
    return {
        "status": severity,
        "alert_count": len(alerts),
        "alerts": [alert.to_dict() for alert in alerts],
    }


def _threshold_alert(name: str, value: float, warn: float, critical: float, message: str) -> list[Alert]:
    if value >= critical:
        return [Alert(name, "critical", value, critical, message)]
    if value >= warn:
        return [Alert(name, "warn", value, warn, message)]
    return []


def _abs_delta_alert(name: str, value: float, warn: float, critical: float, message: str) -> list[Alert]:
    abs_value = abs(value)
    if abs_value >= critical:
        return [Alert(name, "critical", value, critical, message)]
    if abs_value >= warn:
        return [Alert(name, "warn", value, warn, message)]
    return []
