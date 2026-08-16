"""Tests for schema validation."""

import pytest

from im_guard_ml.schema import (
    AuditCase,
    AuditLabel,
    BehaviorKeySummary,
    FinalJudgment,
    HandlingSuggestion,
    RiskLevel,
    TOPICS,
    validate_behavior_key_summary,
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
        assert len(TOPICS) == 13  # 12 violation types + 无主题

    def test_no_topic_included(self):
        assert "无主题" in TOPICS

    def test_core_topics_present(self):
        expected = ["代刷/包榜", "色情诱导", "诈骗引流", "赌博引流", "私下交易"]
        for topic in expected:
            assert topic in TOPICS


class TestValidateLabel:
    def test_valid_safe_label(self):
        label = {
            "risk_level": "low_risk",
            "final_judgment": "not_exist_violation",
            "handling_suggestion": "ignore",
            "topic": "无主题",
        }
        assert validate_label(label) == []

    def test_valid_violation_label(self):
        label = {
            "risk_level": "high_risk",
            "final_judgment": "exist_violation",
            "handling_suggestion": "ban_account",
            "topic": "代刷/包榜",
        }
        assert validate_label(label) == []

    def test_invalid_risk_level(self):
        label = {
            "risk_level": "extreme_risk",
            "final_judgment": "exist_violation",
            "handling_suggestion": "warning",
            "topic": "无主题",
        }
        errors = validate_label(label)
        assert any("risk_level" in e for e in errors)

    def test_ban_requires_high_risk(self):
        label = {
            "risk_level": "mid_risk",
            "final_judgment": "exist_violation",
            "handling_suggestion": "ban_account",
            "topic": "代刷/包榜",
        }
        errors = validate_label(label)
        assert any("ban_account requires high_risk" in e for e in errors)

    def test_not_violation_cannot_ban(self):
        label = {
            "risk_level": "low_risk",
            "final_judgment": "not_exist_violation",
            "handling_suggestion": "ban_account",
            "topic": "无主题",
        }
        errors = validate_label(label)
        assert len(errors) >= 1

    def test_not_violation_cannot_limit(self):
        label = {
            "risk_level": "low_risk",
            "final_judgment": "not_exist_violation",
            "handling_suggestion": "limit_account",
            "topic": "无主题",
        }
        errors = validate_label(label)
        assert any("not_exist_violation" in e for e in errors)


class TestBehaviorKeySummary:
    def test_from_dict_complete(self):
        data = {
            "login_behavior": "异地登录。",
            "search_behavior": "搜索 UID。",
            "follow_behavior": "关注。",
            "enter_room_behavior": "进入对方房间。",
            "mic_interact_behavior": "无互动。",
            "t_bean_consume": "极大额消费。",
            "reward_behavior": "持续高频大额打赏。",
            "gift_total_value": 10000,
            "gift_total_count": 5,
        }
        summary = BehaviorKeySummary.from_dict(data)
        assert summary.login_behavior == "异地登录。"
        assert summary.gift_total_value == 10000.0
        assert summary.gift_total_count == 5

    def test_from_dict_empty(self):
        summary = BehaviorKeySummary.from_dict({})
        assert summary.login_behavior == ""
        assert summary.gift_total_value == 0.0
        assert summary.gift_total_count == 0

    def test_to_dict_roundtrip(self):
        data = {
            "login_behavior": "本机登录。",
            "search_behavior": "",
            "follow_behavior": "互关。",
            "enter_room_behavior": "",
            "mic_interact_behavior": "",
            "t_bean_consume": "中等额度消费。",
            "reward_behavior": "近 7 日累计 3 次礼物。",
            "gift_total_value": 320,
            "gift_total_count": 3,
        }
        summary = BehaviorKeySummary.from_dict(data)
        result = summary.to_dict()
        assert result["gift_total_value"] == 320.0
        assert result["gift_total_count"] == 3

    def test_has_abnormal_signals(self):
        summary = BehaviorKeySummary.from_dict({
            "login_behavior": "异地登录。",
            "t_bean_consume": "极大额消费。",
        })
        assert summary.has_abnormal_signals() is True

    def test_no_abnormal_signals(self):
        summary = BehaviorKeySummary.from_dict({
            "login_behavior": "本机登录。",
            "t_bean_consume": "无消费。",
        })
        assert summary.has_abnormal_signals() is False


class TestValidateBehaviorKeySummary:
    def test_valid_summary(self):
        data = {
            "login_behavior": "本机登录。",
            "gift_total_value": 500,
            "gift_total_count": 3,
        }
        assert validate_behavior_key_summary(data) == []

    def test_invalid_type(self):
        errors = validate_behavior_key_summary("not a dict")
        assert len(errors) == 1

    def test_negative_gift_value(self):
        data = {"gift_total_value": -100}
        errors = validate_behavior_key_summary(data)
        assert any("negative" in e for e in errors)

    def test_wrong_field_type(self):
        data = {"login_behavior": 123}  # Should be str
        errors = validate_behavior_key_summary(data)
        assert any("login_behavior" in e for e in errors)


class TestAuditLabel:
    def test_safe_default(self):
        label = AuditLabel.safe_default()
        assert label.risk_level == "low_risk"
        assert label.final_judgment == "not_exist_violation"
        assert label.handling_suggestion == "ignore"

    def test_to_dict(self):
        label = AuditLabel(
            risk_level="high_risk",
            topic="代刷/包榜",
            final_judgment="exist_violation",
            handling_suggestion="ban_account",
            correlation_analysis="语义+行为完全吻合。",
            judgment_basis="明确代刷约定。",
        )
        d = label.to_dict()
        assert d["risk_level"] == "high_risk"
        assert d["topic"] == "代刷/包榜"
        assert d["correlation_analysis"] == "语义+行为完全吻合。"


class TestAuditCase:
    def test_from_dict_minimal(self):
        data = {
            "ticket_id": "test-001",
            "audit_scene": {"chat_type": "IM私聊"},
            "chat_evidence_list": [],
            "behavior_abnormal_list": [],
        }
        case = AuditCase.from_dict(data)
        assert case.ticket_id == "test-001"
        assert case.label is None

    def test_from_dict_with_label(self):
        data = {
            "ticket_id": "test-002",
            "audit_scene": {},
            "chat_evidence_list": [{"original_content": "test"}],
            "behavior_abnormal_list": [],
            "label": {
                "risk_level": "mid_risk",
                "topic": "私下交易",
                "final_judgment": "exist_violation",
                "handling_suggestion": "warning",
            },
        }
        case = AuditCase.from_dict(data)
        assert case.label is not None
        assert case.label.risk_level == "mid_risk"
        assert case.label.topic == "私下交易"

    def test_roundtrip(self):
        data = {
            "ticket_id": "test-003",
            "audit_scene": {"chat_type": "IM私聊"},
            "chat_evidence_list": [{"original_content": "hello"}],
            "behavior_abnormal_list": [],
            "source": "test",
        }
        case = AuditCase.from_dict(data)
        result = case.to_dict()
        assert result["ticket_id"] == "test-003"
        assert result["source"] == "test"
