from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from enum import StrEnum
except ImportError:  # Python < 3.11
    class StrEnum(str, Enum):
        pass


class RiskLevel(StrEnum):
    LOW = "low_risk"
    MID = "mid_risk"
    HIGH = "high_risk"


class EventJudgment(StrEnum):
    RISK_EVENT = "risk_event"
    NOT_RISK_EVENT = "not_risk_event"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    # legacy 成员名别名（同值 alias，过渡期兼容 AttributeError）
    EXIST_VIOLATION = "risk_event"
    NOT_EXIST_VIOLATION = "not_risk_event"


class RecommendedAction(StrEnum):
    INFORMATION_REPLY = "information_reply"
    COLLECT_MORE_EVIDENCE = "collect_more_evidence"
    SERVICE_FOLLOWUP = "service_followup"
    CREATE_WORK_ORDER = "create_work_order"
    EXPERT_REVIEW = "expert_review"
    EMERGENCY_REVIEW = "emergency_review"
    # legacy 成员名别名（同值 alias，过渡期兼容）
    IGNORE = "information_reply"
    WARNING = "service_followup"
    LIMIT_ACCOUNT = "create_work_order"
    BAN_ACCOUNT = "emergency_review"


# 首期车辆风险主题（ADR-001）：不含重大客诉（走 service_escalation_flags）。
EVENT_TOPICS = [
    "动力电池与热安全",
    "充电与高压系统异常",
    "制动与转向异常",
    "行驶中动力异常",
    "智能驾驶与驾驶辅助反馈",
    "车机、座舱和远程控车故障",
    "重复维修与问题未解决",
    "道路救援与人员安全",
    "质保、零部件与服务争议",
    "无风险事件",
]

SERVICE_ESCALATION_FLAGS = [
    "repeated_complaint",
    "unresolved_service_case",
    "public_opinion_risk",
]

EVIDENCE_REF_SOURCES = {
    "conversation_evidence",
    "vehicle_signal_summary",
    "fault_evidence",
    "service_history_summary",
    "service_context",
    "vehicle_context",
}

# 兼容旧导入名（过渡期）；新代码请使用 EVENT_TOPICS / EventJudgment / RecommendedAction。
TOPICS = EVENT_TOPICS
FinalJudgment = EventJudgment
HandlingSuggestion = RecommendedAction


@dataclass(slots=True)
class CaseLabel:
    """模型侧结构化输出（不含策略层 requires_human_review / route / final_action）。"""

    risk_level: str
    event_topic: str
    event_judgment: str
    recommended_action: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    correlation_analysis: str = ""
    uncertainty_reason: str = ""
    service_escalation_flags: list[str] = field(default_factory=list)

    @classmethod
    def safe_default(cls) -> "CaseLabel":
        return cls(
            risk_level=RiskLevel.LOW.value,
            event_topic="无风险事件",
            event_judgment=EventJudgment.NOT_RISK_EVENT.value,
            recommended_action=RecommendedAction.INFORMATION_REPLY.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "event_topic": self.event_topic,
            "event_judgment": self.event_judgment,
            "recommended_action": self.recommended_action,
            "evidence_refs": list(self.evidence_refs),
            "correlation_analysis": self.correlation_analysis,
            "uncertainty_reason": self.uncertainty_reason,
            "service_escalation_flags": list(self.service_escalation_flags),
        }


# 兼容旧名
AuditLabel = CaseLabel


@dataclass(slots=True)
class ServiceCase:
    """售后服务事件输入（多证据）。"""

    case_id: str
    service_context: dict[str, Any] = field(default_factory=dict)
    vehicle_context: dict[str, Any] = field(default_factory=dict)
    conversation_evidence: list[dict[str, Any]] = field(default_factory=list)
    vehicle_signal_summary: dict[str, Any] = field(default_factory=dict)
    fault_evidence: list[dict[str, Any]] = field(default_factory=list)
    service_history_summary: dict[str, Any] = field(default_factory=dict)
    missing_and_conflicts: dict[str, Any] = field(default_factory=dict)
    data_provenance: dict[str, Any] = field(default_factory=dict)
    label: CaseLabel | None = None
    hint_topic: str | None = None
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "ServiceCase":
        label_obj = obj.get("label")
        label = None
        if isinstance(label_obj, dict):
            label = CaseLabel(
                risk_level=label_obj.get("risk_level", RiskLevel.LOW.value),
                event_topic=label_obj.get("event_topic")
                or label_obj.get("topic", "无风险事件"),
                event_judgment=label_obj.get("event_judgment")
                or label_obj.get("final_judgment", EventJudgment.NOT_RISK_EVENT.value),
                recommended_action=label_obj.get("recommended_action")
                or label_obj.get("handling_suggestion", RecommendedAction.INFORMATION_REPLY.value),
                evidence_refs=list(label_obj.get("evidence_refs") or []),
                correlation_analysis=label_obj.get("correlation_analysis", ""),
                uncertainty_reason=label_obj.get("uncertainty_reason")
                or label_obj.get("judgment_basis", ""),
                service_escalation_flags=list(label_obj.get("service_escalation_flags") or []),
            )
            # legacy 枚举值映射到 AutoCare（仅输入兼容，不鼓励新数据继续用）。
            label = _normalize_legacy_label(label)

        known = {
            "case_id",
            "ticket_id",
            "service_context",
            "vehicle_context",
            "conversation_evidence",
            "vehicle_signal_summary",
            "fault_evidence",
            "service_history_summary",
            "missing_and_conflicts",
            "data_provenance",
            "audit_scene",
            "chat_evidence_list",
            "behavior_abnormal_list",
            "label",
            "hint_topic",
            "source",
        }
        case_id = str(obj.get("case_id") or obj.get("ticket_id") or "")
        service_context = obj.get("service_context") or obj.get("audit_scene") or {}
        conversation = obj.get("conversation_evidence") or obj.get("chat_evidence_list") or []
        return cls(
            case_id=case_id,
            service_context=service_context if isinstance(service_context, dict) else {},
            vehicle_context=obj.get("vehicle_context") or {},
            conversation_evidence=list(conversation) if isinstance(conversation, list) else [],
            vehicle_signal_summary=obj.get("vehicle_signal_summary") or {},
            fault_evidence=list(obj.get("fault_evidence") or []),
            service_history_summary=obj.get("service_history_summary") or {},
            missing_and_conflicts=obj.get("missing_and_conflicts") or {},
            data_provenance=obj.get("data_provenance") or {},
            label=label,
            hint_topic=obj.get("hint_topic"),
            source=obj.get("source", ""),
            extra={k: v for k, v in obj.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        obj: dict[str, Any] = {
            "case_id": self.case_id,
            "service_context": self.service_context,
            "vehicle_context": self.vehicle_context,
            "conversation_evidence": self.conversation_evidence,
            "vehicle_signal_summary": self.vehicle_signal_summary,
            "fault_evidence": self.fault_evidence,
            "service_history_summary": self.service_history_summary,
            "missing_and_conflicts": self.missing_and_conflicts,
            "data_provenance": self.data_provenance,
            "source": self.source,
        }
        if self.hint_topic:
            obj["hint_topic"] = self.hint_topic
        if self.label:
            obj["label"] = self.label.to_dict()
        obj.update(self.extra)
        return obj

    def has_vehicle_side_evidence(self) -> bool:
        """是否存在可用于紧急门禁的车辆侧证据（摘要告警或故障）。"""
        signal = self.vehicle_signal_summary or {}
        warnings = signal.get("warning_lights") or []
        if isinstance(warnings, list) and any(str(x).strip() for x in warnings):
            return True
        freshness = str(signal.get("data_freshness") or "").lower()
        charging = str(signal.get("charging_status") or "").lower()
        safety = str(signal.get("safety_system_status") or "").lower()
        if any(token in charging for token in ("interrupt", "fault", "abnormal", "中断", "异常")):
            return True
        if any(token in safety for token in ("warn", "critical", "fault", "告警", "异常")):
            return True
        # 有新鲜摘要且充电/安全状态非空闲，视为可用车辆侧证据
        if freshness in {"fresh", "near_realtime", "current"} and (
            charging not in {"", "unknown", "normal"} or safety not in {"", "unknown", "normal"}
        ):
            return True
        faults = self.fault_evidence or []
        for item in faults:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity_from_source") or "").lower()
            if sev in {"warning", "critical"}:
                return True
            if str(item.get("fault_domain") or "").strip():
                return True
        return False


AuditCase = ServiceCase


def _normalize_legacy_label(label: CaseLabel) -> CaseLabel:
    """把残留的 legacy 枚举映射到 AutoCare（仅兼容旧 fixture）。"""
    judgment_map = {
        "exist_violation": EventJudgment.RISK_EVENT.value,
        "not_exist_violation": EventJudgment.NOT_RISK_EVENT.value,
    }
    action_map = {
        "ignore": RecommendedAction.INFORMATION_REPLY.value,
        "warning": RecommendedAction.SERVICE_FOLLOWUP.value,
        "limit_account": RecommendedAction.CREATE_WORK_ORDER.value,
        "ban_account": RecommendedAction.EMERGENCY_REVIEW.value,
    }
    topic_map = {
        "无主题": "无风险事件",
    }
    data = label.to_dict()
    data["event_judgment"] = judgment_map.get(data["event_judgment"], data["event_judgment"])
    data["recommended_action"] = action_map.get(data["recommended_action"], data["recommended_action"])
    data["event_topic"] = topic_map.get(data["event_topic"], data["event_topic"])
    return CaseLabel(**data)


def validate_evidence_refs(refs: Any, case: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if refs is None:
        return errors
    if not isinstance(refs, list):
        return ["evidence_refs must be a list"]
    case = case or {}
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"evidence_refs[{i}] must be an object")
            continue
        source = ref.get("source")
        if source not in EVIDENCE_REF_SOURCES:
            errors.append(f"evidence_refs[{i}].source must be one of allowed evidence sources")
            continue
        if "index" in ref and source in {
            "conversation_evidence",
            "fault_evidence",
        }:
            try:
                idx = int(ref["index"])
            except (TypeError, ValueError):
                errors.append(f"evidence_refs[{i}].index must be an integer")
                continue
            bucket = case.get(source) or []
            if isinstance(bucket, list) and (idx < 0 or idx >= len(bucket)):
                errors.append(f"evidence_refs[{i}] index out of range for {source}")
        field_name = ref.get("field")
        if field_name is not None and not isinstance(field_name, str):
            errors.append(f"evidence_refs[{i}].field must be a string")
    return errors


def validate_label(label: dict[str, Any], case: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    # 兼容旧字段名读入，并 remap legacy 枚举值（与 parsing._canonicalize / CaseLabel 路径一致）
    normalized = dict(label)
    if "event_topic" not in normalized and "topic" in normalized:
        normalized["event_topic"] = normalized["topic"]
    if "event_judgment" not in normalized and "final_judgment" in normalized:
        normalized["event_judgment"] = normalized["final_judgment"]
    if "recommended_action" not in normalized and "handling_suggestion" in normalized:
        normalized["recommended_action"] = normalized["handling_suggestion"]
    judgment_map = {
        "exist_violation": EventJudgment.RISK_EVENT.value,
        "not_exist_violation": EventJudgment.NOT_RISK_EVENT.value,
    }
    action_map = {
        "ignore": RecommendedAction.INFORMATION_REPLY.value,
        "warning": RecommendedAction.SERVICE_FOLLOWUP.value,
        "limit_account": RecommendedAction.CREATE_WORK_ORDER.value,
        "ban_account": RecommendedAction.EMERGENCY_REVIEW.value,
    }
    topic_map = {"无主题": "无风险事件"}
    if normalized.get("event_judgment") in judgment_map:
        normalized["event_judgment"] = judgment_map[normalized["event_judgment"]]
    if normalized.get("recommended_action") in action_map:
        normalized["recommended_action"] = action_map[normalized["recommended_action"]]
    if normalized.get("event_topic") in topic_map:
        normalized["event_topic"] = topic_map[normalized["event_topic"]]

    if normalized.get("risk_level") not in {x.value for x in RiskLevel}:
        errors.append("risk_level must be low_risk, mid_risk, or high_risk")
    if normalized.get("event_judgment") not in {x.value for x in EventJudgment}:
        errors.append(
            "event_judgment must be risk_event, not_risk_event, or insufficient_evidence"
        )
    if normalized.get("recommended_action") not in {x.value for x in RecommendedAction}:
        errors.append("recommended_action must be a configured service action")
    topic = normalized.get("event_topic", "无风险事件")
    if topic not in EVENT_TOPICS:
        errors.append("event_topic must be one of the configured vehicle risk topics")

    judgment = normalized.get("event_judgment")
    action = normalized.get("recommended_action")
    risk = normalized.get("risk_level")

    if judgment == EventJudgment.NOT_RISK_EVENT.value:
        if action not in {
            RecommendedAction.INFORMATION_REPLY.value,
            RecommendedAction.SERVICE_FOLLOWUP.value,
        }:
            errors.append("not_risk_event should not route to work_order/expert/emergency")
        if risk not in {RiskLevel.LOW.value, RiskLevel.MID.value}:
            errors.append("not_risk_event should not be high_risk without stronger evidence path")

    if judgment == EventJudgment.INSUFFICIENT_EVIDENCE.value:
        if action not in {
            RecommendedAction.COLLECT_MORE_EVIDENCE.value,
            RecommendedAction.SERVICE_FOLLOWUP.value,
            RecommendedAction.EXPERT_REVIEW.value,
        }:
            errors.append(
                "insufficient_evidence should prefer collect_more_evidence, followup, or expert_review"
            )

    if judgment == EventJudgment.RISK_EVENT.value:
        if risk not in {RiskLevel.MID.value, RiskLevel.HIGH.value}:
            errors.append("risk_event requires mid_risk or high_risk")
        if action == RecommendedAction.INFORMATION_REPLY.value:
            errors.append("risk_event cannot route to information_reply only")

    if action == RecommendedAction.EMERGENCY_REVIEW.value:
        if risk != RiskLevel.HIGH.value or judgment != EventJudgment.RISK_EVENT.value:
            errors.append("emergency_review requires high_risk and risk_event")

    flags = normalized.get("service_escalation_flags") or []
    if flags and not isinstance(flags, list):
        errors.append("service_escalation_flags must be a list")
    elif isinstance(flags, list):
        for flag in flags:
            if flag not in SERVICE_ESCALATION_FLAGS:
                errors.append(f"unknown service_escalation_flag: {flag}")

    errors.extend(validate_evidence_refs(normalized.get("evidence_refs"), case))
    return errors
