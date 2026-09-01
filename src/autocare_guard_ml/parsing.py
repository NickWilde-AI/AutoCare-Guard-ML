from __future__ import annotations

import json
import re
from typing import Any

from .schema import (
    CaseLabel,
    EventJudgment,
    RecommendedAction,
    RiskLevel,
    validate_label,
)


ENUM_PATTERNS = {
    "risk_level": r"(low_risk|mid_risk|high_risk)",
    "event_judgment": r"(risk_event|not_risk_event|insufficient_evidence)",
    "recommended_action": (
        r"(information_reply|collect_more_evidence|service_followup|"
        r"create_work_order|expert_review|emergency_review)"
    ),
}


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _canonicalize(parsed: dict[str, Any]) -> dict[str, Any]:
    out = dict(parsed)
    # 旧字段优先覆盖（即使 default 已填了新字段名）
    if "topic" in out:
        out["event_topic"] = out.pop("topic")
    if "final_judgment" in out:
        out["event_judgment"] = out.pop("final_judgment")
    if "handling_suggestion" in out:
        out["recommended_action"] = out.pop("handling_suggestion")
    if "judgment_basis" in out and not out.get("uncertainty_reason"):
        out["uncertainty_reason"] = out.pop("judgment_basis")
    elif "judgment_basis" in out:
        out.pop("judgment_basis", None)
    # legacy enum remap
    legacy_j = {
        "exist_violation": EventJudgment.RISK_EVENT.value,
        "not_exist_violation": EventJudgment.NOT_RISK_EVENT.value,
    }
    legacy_a = {
        "ignore": RecommendedAction.INFORMATION_REPLY.value,
        "warning": RecommendedAction.SERVICE_FOLLOWUP.value,
        "limit_account": RecommendedAction.CREATE_WORK_ORDER.value,
        "ban_account": RecommendedAction.EMERGENCY_REVIEW.value,
    }
    if out.get("event_judgment") in legacy_j:
        out["event_judgment"] = legacy_j[out["event_judgment"]]
    if out.get("recommended_action") in legacy_a:
        out["recommended_action"] = legacy_a[out["recommended_action"]]
    if out.get("event_topic") == "无主题":
        out["event_topic"] = "无风险事件"
    out.setdefault("evidence_refs", [])
    out.setdefault("service_escalation_flags", [])
    out.setdefault("correlation_analysis", "")
    out.setdefault("uncertainty_reason", "")
    return out


def parse_judge_output(text: str, strict: bool = False) -> dict[str, Any]:
    default = CaseLabel.safe_default().to_dict()
    parsed: dict[str, Any] | None = None
    json_text = _extract_json_object(text)
    if json_text:
        try:
            obj = json.loads(json_text)
            if isinstance(obj, dict):
                parsed = _canonicalize({**default, **obj})
        except json.JSONDecodeError:
            parsed = None
    if parsed is None:
        parsed = dict(default)
        for field, pattern in ENUM_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                parsed[field] = match.group(1)
        parsed = _canonicalize(parsed)
    errors = validate_label(parsed)
    if errors and strict:
        raise ValueError("; ".join(errors))
    if errors:
        if parsed.get("recommended_action") == RecommendedAction.EMERGENCY_REVIEW.value:
            parsed["recommended_action"] = RecommendedAction.EXPERT_REVIEW.value
        if parsed.get("event_judgment") == EventJudgment.NOT_RISK_EVENT.value:
            parsed["risk_level"] = RiskLevel.LOW.value
            parsed["recommended_action"] = RecommendedAction.INFORMATION_REPLY.value
        if parsed.get("event_judgment") == EventJudgment.INSUFFICIENT_EVIDENCE.value:
            if parsed.get("recommended_action") == RecommendedAction.EMERGENCY_REVIEW.value:
                parsed["recommended_action"] = RecommendedAction.COLLECT_MORE_EVIDENCE.value
        if parsed.get("event_judgment") == EventJudgment.RISK_EVENT.value:
            if parsed.get("risk_level") == RiskLevel.LOW.value:
                parsed["risk_level"] = RiskLevel.MID.value
            if parsed.get("recommended_action") == RecommendedAction.INFORMATION_REPLY.value:
                parsed["recommended_action"] = RecommendedAction.SERVICE_FOLLOWUP.value
    return parsed
