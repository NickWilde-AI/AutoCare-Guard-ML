from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .parsing import parse_judge_output
from .schema import (
    EVENT_TOPICS,
    EventJudgment,
    RecommendedAction,
    RiskLevel,
    ServiceCase,
    validate_label,
)


@dataclass(slots=True)
class PostprocessResult:
    parsed_output: dict[str, Any]
    parse_status: str
    validation_errors: list[str]
    route: str
    final_action: str
    requires_human_review: bool
    review_role_hint: str
    review_priority: str
    policy_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.parsed_output,
            "parse_status": self.parse_status,
            "validation_errors": self.validation_errors,
            "route": self.route,
            "final_action": self.final_action,
            "requires_human_review": self.requires_human_review,
            "review_role_hint": self.review_role_hint,
            "review_priority": self.review_priority,
            "policy_reasons": self.policy_reasons,
        }


def postprocess_model_output(raw_output: str, case: dict[str, Any] | None = None) -> PostprocessResult:
    """从模型原始文本出发的完整后处理（解析 → 校验 → 纠错 → 路由）。"""
    return postprocess_prediction(parse_judge_output(raw_output), case)


def postprocess_prediction(parsed: dict[str, Any], case: dict[str, Any] | None = None) -> PostprocessResult:
    """对已解析的预测 dict 执行校验、纠错与策略路由。

    requires_human_review / route / final_action 由策略层生成，模型无最终解释权。
    """
    case = case or {}
    errors = validate_label(parsed, case)
    errors.extend(_input_sensitive_errors(parsed, case))
    parse_status = "ok" if not errors else "corrected"
    corrected = _correct_for_production(parsed, errors, case)
    route, final_action, requires_human, role_hint, priority, reasons = route_policy(
        corrected, case, errors
    )
    return PostprocessResult(
        parsed_output=corrected,
        parse_status=parse_status,
        validation_errors=errors,
        route=route,
        final_action=final_action,
        requires_human_review=requires_human,
        review_role_hint=role_hint,
        review_priority=priority,
        policy_reasons=reasons,
    )


def route_policy(
    label: dict[str, Any],
    case: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> tuple[str, str, bool, str, str, list[str]]:
    errors = errors or []
    case = case or {}
    reasons: list[str] = []
    action = label.get("recommended_action")
    judgment = label.get("event_judgment")
    flags = label.get("service_escalation_flags") or []

    if errors:
        reasons.extend(errors)
        if action == RecommendedAction.EMERGENCY_REVIEW.value:
            return (
                "review_queue",
                "await_human_confirmation",
                True,
                "safety_reviewer",
                "urgent",
                reasons + ["emergency_candidate_with_validation_errors"],
            )
        return (
            "fallback_or_review",
            "defer_to_rule_engine",
            True,
            "technical_expert",
            "high",
            reasons,
        )

    if action == RecommendedAction.INFORMATION_REPLY.value:
        role = "service_manager" if flags else "technical_expert"
        return "information_flow", "information_reply_candidate", bool(flags), role, "normal", reasons
    if action == RecommendedAction.COLLECT_MORE_EVIDENCE.value:
        return (
            "collect_evidence",
            "request_more_evidence",
            False,
            "technical_expert",
            "normal",
            reasons,
        )
    if action == RecommendedAction.SERVICE_FOLLOWUP.value:
        return "service_queue", "service_followup_candidate", False, "technical_expert", "normal", reasons
    if action == RecommendedAction.CREATE_WORK_ORDER.value:
        return "work_order_queue", "create_work_order_candidate", False, "technical_expert", "normal", reasons
    if action == RecommendedAction.EXPERT_REVIEW.value:
        return "review_queue", "await_expert_review", True, "technical_expert", "high", reasons
    if action == RecommendedAction.EMERGENCY_REVIEW.value:
        return (
            "review_queue",
            "await_human_confirmation",
            True,
            "safety_reviewer",
            "urgent",
            reasons + ["emergency_review_gated"],
        )
    if judgment == EventJudgment.INSUFFICIENT_EVIDENCE.value:
        return (
            "collect_evidence",
            "request_more_evidence",
            False,
            "technical_expert",
            "normal",
            reasons,
        )
    return "fallback_or_review", "defer_to_rule_engine", True, "technical_expert", "high", reasons


def _correct_for_production(
    label: dict[str, Any], errors: list[str], case: dict[str, Any]
) -> dict[str, Any]:
    corrected = dict(label)
    if corrected.get("event_topic") not in EVENT_TOPICS:
        corrected["event_topic"] = "无风险事件"

    if corrected.get("event_judgment") == EventJudgment.NOT_RISK_EVENT.value:
        corrected["risk_level"] = RiskLevel.LOW.value
        if corrected.get("recommended_action") not in {
            RecommendedAction.INFORMATION_REPLY.value,
            RecommendedAction.SERVICE_FOLLOWUP.value,
        }:
            corrected["recommended_action"] = RecommendedAction.INFORMATION_REPLY.value

    if corrected.get("event_judgment") == EventJudgment.INSUFFICIENT_EVIDENCE.value:
        if corrected.get("recommended_action") == RecommendedAction.EMERGENCY_REVIEW.value:
            corrected["recommended_action"] = RecommendedAction.COLLECT_MORE_EVIDENCE.value

    if corrected.get("recommended_action") == RecommendedAction.EMERGENCY_REVIEW.value:
        if (
            corrected.get("risk_level") != RiskLevel.HIGH.value
            or corrected.get("event_judgment") != EventJudgment.RISK_EVENT.value
        ):
            corrected["recommended_action"] = RecommendedAction.EXPERT_REVIEW.value
        elif any("vehicle-side evidence missing" in e for e in errors):
            corrected["recommended_action"] = RecommendedAction.EXPERT_REVIEW.value
    return corrected


def _input_sensitive_errors(label: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """紧急动作证据门禁：无车辆侧证据不得仅凭文本进入 emergency_review。"""
    errors: list[str] = []
    if label.get("recommended_action") != RecommendedAction.EMERGENCY_REVIEW.value:
        return errors
    service_case = ServiceCase.from_dict(case)
    if not service_case.has_vehicle_side_evidence():
        errors.append("vehicle-side evidence missing for emergency_review")
    # high-risk / emergency 应至少有一条 evidence_refs
    refs = label.get("evidence_refs") or []
    if not refs:
        errors.append("emergency_review requires at least one evidence_ref")
    return errors
