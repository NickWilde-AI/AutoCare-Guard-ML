from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .parsing import parse_judge_output
from .schema import FinalJudgment, HandlingSuggestion, RiskLevel, TOPICS, validate_label


@dataclass(slots=True)
class PostprocessResult:
    parsed_output: dict[str, Any]
    parse_status: str
    validation_errors: list[str]
    route: str
    final_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.parsed_output,
            "parse_status": self.parse_status,
            "validation_errors": self.validation_errors,
            "route": self.route,
            "final_action": self.final_action,
        }


def postprocess_model_output(raw_output: str, case: dict[str, Any] | None = None) -> PostprocessResult:
    """从模型原始文本出发的完整后处理（解析 → 校验 → 纠错 → 路由）。"""
    return postprocess_prediction(parse_judge_output(raw_output), case)


def postprocess_prediction(parsed: dict[str, Any], case: dict[str, Any] | None = None) -> PostprocessResult:
    """对已解析的预测 dict 执行校验、纠错与路由（服务层统一入口，P1-01）。

    /judge 与 CLI predict 都必须经过本函数，保证 ban 三重保护与
    parse_status 可观测性在生产路径生效，而不是只在测试里生效。
    """
    errors = validate_label(parsed)
    errors.extend(_input_sensitive_errors(parsed, case or {}))
    parse_status = "ok" if not errors else "corrected"
    corrected = _correct_for_production(parsed, errors)
    route, final_action = route_policy(corrected, case or {}, errors)
    return PostprocessResult(
        parsed_output=corrected,
        parse_status=parse_status,
        validation_errors=errors,
        route=route,
        final_action=final_action,
    )


def route_policy(label: dict[str, Any], case: dict[str, Any] | None = None, errors: list[str] | None = None) -> tuple[str, str]:
    errors = errors or []
    if errors:
        if label.get("handling_suggestion") == HandlingSuggestion.BAN_ACCOUNT.value:
            return "human_review_required", "review_before_ban"
        return "fallback_or_review", "defer_to_rule_engine"
    suggestion = label.get("handling_suggestion")
    if suggestion == HandlingSuggestion.IGNORE.value:
        return "auto_close", "ignore"
    if suggestion == HandlingSuggestion.WARNING.value:
        return "auto_action", "send_warning"
    if suggestion == HandlingSuggestion.LIMIT_ACCOUNT.value:
        return "policy_action", "limit_account_candidate"
    if suggestion == HandlingSuggestion.BAN_ACCOUNT.value:
        return "human_review_required", "review_before_ban"
    return "fallback_or_review", "defer_to_rule_engine"


def _correct_for_production(label: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    corrected = dict(label)
    if corrected.get("topic") not in TOPICS:
        corrected["topic"] = "无主题"
    if corrected.get("final_judgment") == FinalJudgment.NOT_VIOLATION.value:
        corrected["risk_level"] = RiskLevel.LOW.value
        corrected["handling_suggestion"] = HandlingSuggestion.IGNORE.value
    if corrected.get("handling_suggestion") == HandlingSuggestion.BAN_ACCOUNT.value:
        if corrected.get("risk_level") != RiskLevel.HIGH.value or corrected.get("final_judgment") != FinalJudgment.VIOLATION.value:
            corrected["handling_suggestion"] = HandlingSuggestion.LIMIT_ACCOUNT.value
    if errors and "behavior evidence missing for ban_account" in errors:
        corrected["handling_suggestion"] = HandlingSuggestion.LIMIT_ACCOUNT.value
    return corrected


# 构成 ban 行为证据的异常信号（P2-12：普通描述如"本机登录。"不算证据）。
_BAN_BEHAVIOR_MARKERS = ("极大额", "大额", "高频", "异地", "批量", "短时间")
_BAN_MIN_GIFT_VALUE = 5000.0


def _input_sensitive_errors(label: dict[str, Any], case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if label.get("handling_suggestion") == HandlingSuggestion.BAN_ACCOUNT.value:
        behavior_abnormal = case.get("behavior_abnormal_list") or []
        summary = case.get("audit_scene", {}).get("behavior_key_summary", {})
        gift_value = _as_float(summary.get("gift_total_value"))
        signal_text = f"{summary.get('reward_behavior', '')} {summary.get('login_behavior', '')}"
        has_behavior = (
            bool(behavior_abnormal)
            or (gift_value is not None and gift_value >= _BAN_MIN_GIFT_VALUE)
            or any(marker in signal_text for marker in _BAN_BEHAVIOR_MARKERS)
        )
        if not has_behavior:
            errors.append("behavior evidence missing for ban_account")
    return errors


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

