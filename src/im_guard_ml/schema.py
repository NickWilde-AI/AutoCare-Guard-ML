from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    LOW = "low_risk"
    MID = "mid_risk"
    HIGH = "high_risk"


class FinalJudgment(StrEnum):
    NOT_VIOLATION = "not_exist_violation"
    VIOLATION = "exist_violation"


class HandlingSuggestion(StrEnum):
    IGNORE = "ignore"
    WARNING = "warning"
    LIMIT_ACCOUNT = "limit_account"
    BAN_ACCOUNT = "ban_account"


TOPICS = [
    "代刷/包榜",
    "色情诱导",
    "诈骗引流",
    "赌博引流",
    "私下交易",
    "政治敏感",
    "辱骂攻击",
    "未成年保护",
    "版权侵犯",
    "虚假信息",
    "自伤诱导",
    "违禁品交易",
    "无主题",
]


# ---------------------------------------------------------------------------
# Behavior key summary schema
# ---------------------------------------------------------------------------

# Required fields in behavior_key_summary with their expected types
BEHAVIOR_KEY_FIELDS: dict[str, type | tuple[type, ...]] = {
    "login_behavior": str,
    "search_behavior": str,
    "follow_behavior": str,
    "enter_room_behavior": str,
    "mic_interact_behavior": str,
    "t_bean_consume": str,
    "reward_behavior": str,
    "gift_total_value": (int, float),
    "gift_total_count": (int, float),
}


@dataclass(slots=True)
class BehaviorKeySummary:
    """Structured representation of user behavior signals within the audit window."""
    login_behavior: str = ""
    search_behavior: str = ""
    follow_behavior: str = ""
    enter_room_behavior: str = ""
    mic_interact_behavior: str = ""
    t_bean_consume: str = ""
    reward_behavior: str = ""
    gift_total_value: float = 0.0
    gift_total_count: int = 0

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "BehaviorKeySummary":
        return cls(
            login_behavior=str(obj.get("login_behavior", "") or ""),
            search_behavior=str(obj.get("search_behavior", "") or ""),
            follow_behavior=str(obj.get("follow_behavior", "") or ""),
            enter_room_behavior=str(obj.get("enter_room_behavior", "") or ""),
            mic_interact_behavior=str(obj.get("mic_interact_behavior", "") or ""),
            t_bean_consume=str(obj.get("t_bean_consume", "") or ""),
            reward_behavior=str(obj.get("reward_behavior", "") or ""),
            gift_total_value=float(obj.get("gift_total_value", 0) or 0),
            gift_total_count=int(obj.get("gift_total_count", 0) or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "login_behavior": self.login_behavior,
            "search_behavior": self.search_behavior,
            "follow_behavior": self.follow_behavior,
            "enter_room_behavior": self.enter_room_behavior,
            "mic_interact_behavior": self.mic_interact_behavior,
            "t_bean_consume": self.t_bean_consume,
            "reward_behavior": self.reward_behavior,
            "gift_total_value": self.gift_total_value,
            "gift_total_count": self.gift_total_count,
        }

    def has_abnormal_signals(self) -> bool:
        """Check if any behavior signals indicate potential abnormality."""
        high_value_keywords = ("极大额", "大额", "高频", "异地", "批量", "短时间")
        text_fields = (
            self.login_behavior + self.reward_behavior +
            self.t_bean_consume + self.enter_room_behavior
        )
        return any(kw in text_fields for kw in high_value_keywords)


def validate_behavior_key_summary(summary: dict[str, Any]) -> list[str]:
    """Validate behavior_key_summary fields and types.

    Returns list of validation errors (empty if valid).
    """
    errors: list[str] = []
    if not isinstance(summary, dict):
        return ["behavior_key_summary must be a dict"]

    for field_name, expected_type in BEHAVIOR_KEY_FIELDS.items():
        value = summary.get(field_name)
        if value is None:
            continue  # Missing fields are acceptable (default to empty/zero)
        if not isinstance(value, expected_type):
            errors.append(
                f"behavior_key_summary.{field_name}: expected {expected_type.__name__ if isinstance(expected_type, type) else 'number'}, "
                f"got {type(value).__name__}"
            )

    # Numeric range checks
    gift_value = summary.get("gift_total_value")
    if gift_value is not None and isinstance(gift_value, (int, float)) and gift_value < 0:
        errors.append("behavior_key_summary.gift_total_value cannot be negative")

    gift_count = summary.get("gift_total_count")
    if gift_count is not None and isinstance(gift_count, (int, float)) and gift_count < 0:
        errors.append("behavior_key_summary.gift_total_count cannot be negative")

    return errors


@dataclass(slots=True)
class AuditLabel:
    risk_level: str
    topic: str
    final_judgment: str
    handling_suggestion: str
    correlation_analysis: str = ""
    judgment_basis: str = ""

    @classmethod
    def safe_default(cls) -> "AuditLabel":
        return cls(
            risk_level=RiskLevel.LOW.value,
            topic="无主题",
            final_judgment=FinalJudgment.NOT_VIOLATION.value,
            handling_suggestion=HandlingSuggestion.IGNORE.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "topic": self.topic,
            "correlation_analysis": self.correlation_analysis,
            "final_judgment": self.final_judgment,
            "judgment_basis": self.judgment_basis,
            "handling_suggestion": self.handling_suggestion,
        }


@dataclass(slots=True)
class AuditCase:
    ticket_id: str
    audit_scene: dict[str, Any]
    chat_evidence_list: list[dict[str, Any]]
    behavior_abnormal_list: list[dict[str, Any]]
    label: AuditLabel | None = None
    hint_topic: str | None = None
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "AuditCase":
        label_obj = obj.get("label")
        label = None
        if isinstance(label_obj, dict):
            label = AuditLabel(
                risk_level=label_obj.get("risk_level", RiskLevel.LOW.value),
                topic=label_obj.get("topic", "无主题"),
                correlation_analysis=label_obj.get("correlation_analysis", ""),
                final_judgment=label_obj.get("final_judgment", FinalJudgment.NOT_VIOLATION.value),
                judgment_basis=label_obj.get("judgment_basis", ""),
                handling_suggestion=label_obj.get("handling_suggestion", HandlingSuggestion.IGNORE.value),
            )
        known = {
            "ticket_id",
            "audit_scene",
            "chat_evidence_list",
            "behavior_abnormal_list",
            "label",
            "hint_topic",
            "source",
        }
        return cls(
            ticket_id=obj.get("ticket_id", ""),
            audit_scene=obj.get("audit_scene", {}),
            chat_evidence_list=obj.get("chat_evidence_list", []),
            behavior_abnormal_list=obj.get("behavior_abnormal_list", []),
            label=label,
            hint_topic=obj.get("hint_topic"),
            source=obj.get("source", ""),
            extra={k: v for k, v in obj.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        obj = {
            "ticket_id": self.ticket_id,
            "audit_scene": self.audit_scene,
            "chat_evidence_list": self.chat_evidence_list,
            "behavior_abnormal_list": self.behavior_abnormal_list,
            "source": self.source,
        }
        if self.hint_topic:
            obj["hint_topic"] = self.hint_topic
        if self.label:
            obj["label"] = self.label.to_dict()
        obj.update(self.extra)
        return obj


def validate_label(label: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if label.get("risk_level") not in {x.value for x in RiskLevel}:
        errors.append("risk_level must be low_risk, mid_risk, or high_risk")
    if label.get("final_judgment") not in {x.value for x in FinalJudgment}:
        errors.append("final_judgment must be exist_violation or not_exist_violation")
    if label.get("handling_suggestion") not in {x.value for x in HandlingSuggestion}:
        errors.append("handling_suggestion must be ignore, warning, limit_account, or ban_account")
    if label.get("topic", "无主题") not in TOPICS:
        errors.append("topic must be one of the configured business topics")
    if label.get("final_judgment") == FinalJudgment.NOT_VIOLATION.value:
        if label.get("handling_suggestion") not in {HandlingSuggestion.IGNORE.value, HandlingSuggestion.WARNING.value}:
            errors.append("not_exist_violation should not route to limit_account or ban_account")
    if label.get("handling_suggestion") == HandlingSuggestion.BAN_ACCOUNT.value:
        if label.get("risk_level") != RiskLevel.HIGH.value or label.get("final_judgment") != FinalJudgment.VIOLATION.value:
            errors.append("ban_account requires high_risk and exist_violation")
    return errors

