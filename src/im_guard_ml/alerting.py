from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_THRESHOLDS = {
    "ban_account_rate_warn": 0.08,
    "ban_account_rate_critical": 0.12,
    "parse_non_ok_rate_warn": 0.005,
    "parse_non_ok_rate_critical": 0.02,
    "empty_behavior_rate_warn": 0.05,
    "empty_behavior_rate_critical": 0.15,
    "gift_total_value_mean_delta_warn": 1000.0,
    "gift_total_value_mean_delta_critical": 3000.0,
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
            "ban_account_rate",
            float(guards.get("ban_account_rate", 0.0)),
            thresholds["ban_account_rate_warn"],
            thresholds["ban_account_rate_critical"],
            "ban 占比异常，需检查风险分布、上游特征和处置策略。",
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
            "empty_behavior_rate",
            float(guards.get("empty_behavior_rate", 0.0)),
            thresholds["empty_behavior_rate_warn"],
            thresholds["empty_behavior_rate_critical"],
            "行为字段缺失率升高，需检查行为特征服务。",
        )
    )
    if diff:
        alerts.extend(
            _abs_delta_alert(
                "gift_total_value_mean_delta",
                float(diff.get("gift_total_value_mean_delta", 0.0)),
                thresholds["gift_total_value_mean_delta_warn"],
                thresholds["gift_total_value_mean_delta_critical"],
                "礼物金额均值相对 baseline 漂移，需检查消费特征分布。",
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

