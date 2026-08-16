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
    parsed = parse_judge_output(raw_output)
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


def _input_sensitive_errors(label: dict[str, Any], case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if label.get("handling_suggestion") == HandlingSuggestion.BAN_ACCOUNT.value:
        behavior_abnormal = case.get("behavior_abnormal_list") or []
        summary = case.get("audit_scene", {}).get("behavior_key_summary", {})
        has_behavior = bool(behavior_abnormal) or any(
            summary.get(k) not in (None, "", "无", 0)
            for k in ("gift_total_value", "gift_total_count", "reward_behavior", "login_behavior")
        )
        if not has_behavior:
            errors.append("behavior evidence missing for ban_account")
    return errors

