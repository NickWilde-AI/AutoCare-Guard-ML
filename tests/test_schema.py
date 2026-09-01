"""Tests for AutoCare schema validation."""

from im_guard_ml.schema import (
    AuditCase,
    AuditLabel,
    EVENT_TOPICS,
    EventJudgment,
    RecommendedAction,
    RiskLevel,
    ServiceCase,
    TOPICS,
    validate_label,
)


class TestRiskLevel:
    def test_enum_values(self):
        assert RiskLevel.LOW == "low_risk"
        assert RiskLevel.MID == "mid_risk"
        assert RiskLevel.HIGH == "high_risk"

    def test_enum_membership(self):
        assert "low_risk" in {r.value for r in RiskLevel}
        assert "invalid" not in {r.value for r in RiskLevel}


class TestTopics:
    def test_topic_count(self):
        assert len(TOPICS) == 10  # 9 车辆风险主题 + 无风险事件
        assert TOPICS == EVENT_TOPICS

    def test_no_risk_event_included(self):
        assert "无风险事件" in TOPICS

    def test_im_topics_removed(self):
        assert "代刷/包榜" not in TOPICS
        assert "无主题" not in TOPICS

    def test_core_topics_present(self):
        expected = ["动力电池与热安全", "充电与高压系统异常", "制动与转向异常", "道路救援与人员安全"]
        for topic in expected:
            assert topic in TOPICS


class TestValidateLabel:
    def test_valid_safe_label(self):
        label = {
            "risk_level": "low_risk",
            "event_judgment": "not_risk_event",
            "recommended_action": "information_reply",
            "event_topic": "无风险事件",
        }
        assert validate_label(label) == []

    def test_valid_risk_event_label(self):
        label = {
            "risk_level": "high_risk",
            "event_judgment": "risk_event",
            "recommended_action": "emergency_review",
            "event_topic": "动力电池与热安全",
        }
        assert validate_label(label) == []

    def test_legacy_fields_accepted(self):
        # 旧字段名 + 旧 IM 枚举值应被 remap 后通过
        label = {
            "risk_level": "low_risk",
            "final_judgment": "not_exist_violation",
            "handling_suggestion": "ignore",
            "topic": "无主题",
        }
        assert validate_label(label) == []
        # 旧字段名 + 新枚举值
        label2 = {
            "risk_level": "low_risk",
            "final_judgment": "not_risk_event",
            "handling_suggestion": "information_reply",
            "topic": "无风险事件",
        }
        assert validate_label(label2) == []

    def test_invalid_risk_level(self):
        label = {
            "risk_level": "extreme_risk",
            "event_judgment": "risk_event",
            "recommended_action": "service_followup",
            "event_topic": "无风险事件",
        }
        errors = validate_label(label)
        assert any("risk_level" in e for e in errors)

    def test_emergency_requires_high_risk(self):
        label = {
            "risk_level": "mid_risk",
            "event_judgment": "risk_event",
            "recommended_action": "emergency_review",
            "event_topic": "动力电池与热安全",
        }
        errors = validate_label(label)
        assert any("emergency_review requires high_risk" in e for e in errors)

    def test_not_risk_cannot_emergency(self):
        label = {
            "risk_level": "low_risk",
            "event_judgment": "not_risk_event",
            "recommended_action": "emergency_review",
            "event_topic": "无风险事件",
        }
        errors = validate_label(label)
        assert len(errors) >= 1

    def test_not_risk_cannot_work_order(self):
        label = {
            "risk_level": "low_risk",
            "event_judgment": "not_risk_event",
            "recommended_action": "create_work_order",
            "event_topic": "无风险事件",
        }
        errors = validate_label(label)
        assert any("not_risk_event" in e for e in errors)


class TestCaseLabel:
    def test_safe_default(self):
        label = AuditLabel.safe_default()
        assert label.risk_level == "low_risk"
        assert label.event_judgment == EventJudgment.NOT_RISK_EVENT.value
        assert label.recommended_action == RecommendedAction.INFORMATION_REPLY.value

    def test_to_dict(self):
        label = AuditLabel(
            risk_level="high_risk",
            event_topic="动力电池与热安全",
            event_judgment="risk_event",
            recommended_action="emergency_review",
            correlation_analysis="对话与车辆告警同向。",
            uncertainty_reason="焦糊味+电池告警。",
        )
        d = label.to_dict()
        assert d["risk_level"] == "high_risk"
        assert d["event_topic"] == "动力电池与热安全"
        assert d["correlation_analysis"] == "对话与车辆告警同向。"


class TestServiceCase:
    def test_from_dict_minimal(self):
        data = {
            "case_id": "test-001",
            "service_context": {"channel": "app"},
            "conversation_evidence": [],
            "fault_evidence": [],
        }
        case = ServiceCase.from_dict(data)
        assert case.case_id == "test-001"
        assert case.label is None

    def test_from_dict_legacy_fields(self):
        data = {
            "ticket_id": "test-001",
            "audit_scene": {"chat_type": "IM私聊"},
            "chat_evidence_list": [],
            "behavior_abnormal_list": [],
        }
        case = AuditCase.from_dict(data)
        assert case.case_id == "test-001"
        assert case.service_context.get("chat_type") == "IM私聊"

    def test_from_dict_with_label(self):
        data = {
            "case_id": "test-002",
            "service_context": {},
            "conversation_evidence": [{"content": "test"}],
            "fault_evidence": [],
            "label": {
                "risk_level": "mid_risk",
                "event_topic": "充电与高压系统异常",
                "event_judgment": "risk_event",
                "recommended_action": "create_work_order",
            },
        }
        case = ServiceCase.from_dict(data)
        assert case.label is not None
        assert case.label.risk_level == "mid_risk"
        assert case.label.event_topic == "充电与高压系统异常"

    def test_has_vehicle_side_evidence(self):
        case = ServiceCase.from_dict(
            {
                "case_id": "v1",
                "vehicle_signal_summary": {"warning_lights": ["电池过热"]},
            }
        )
        assert case.has_vehicle_side_evidence() is True

    def test_roundtrip(self):
        data = {
            "case_id": "test-003",
            "service_context": {"channel": "hotline"},
            "conversation_evidence": [{"content": "hello"}],
            "fault_evidence": [],
            "source": "test",
        }
        case = ServiceCase.from_dict(data)
        result = case.to_dict()
        assert result["case_id"] == "test-003"
        assert result["source"] == "test"
