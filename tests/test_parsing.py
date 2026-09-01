"""Tests for AutoCare JSON parsing and fallback logic."""

from autocare_guard_ml.parsing import parse_judge_output


class TestParseJudgeOutput:
    def test_valid_json(self):
        text = (
            '{"risk_level": "high_risk", "event_topic": "动力电池与热安全", '
            '"correlation_analysis": "test", "event_judgment": "risk_event", '
            '"uncertainty_reason": "test", "recommended_action": "emergency_review"}'
        )
        result = parse_judge_output(text)
        assert result["risk_level"] == "high_risk"
        assert result["event_judgment"] == "risk_event"
        assert result["recommended_action"] == "emergency_review"
        assert result["event_topic"] == "动力电池与热安全"

    def test_json_with_surrounding_text(self):
        text = (
            'Here is my analysis:\n{"risk_level": "mid_risk", "event_topic": "充电与高压系统异常", '
            '"correlation_analysis": "", "event_judgment": "risk_event", '
            '"uncertainty_reason": "", "recommended_action": "service_followup"}\nDone.'
        )
        result = parse_judge_output(text)
        assert result["risk_level"] == "mid_risk"
        assert result["recommended_action"] == "service_followup"

    def test_legacy_fields_canonicalized(self):
        text = (
            '{"risk_level": "high_risk", "topic": "动力电池与热安全", "correlation_analysis": "test", '
            '"final_judgment": "exist_violation", "judgment_basis": "test", '
            '"handling_suggestion": "ban_account"}'
        )
        result = parse_judge_output(text)
        assert result["event_judgment"] == "risk_event"
        assert result["recommended_action"] in {"emergency_review", "expert_review"}
        assert result["event_topic"] == "动力电池与热安全"

    def test_regex_fallback(self):
        text = "risk_level is high_risk and event_judgment is risk_event with emergency_review"
        result = parse_judge_output(text)
        assert result["risk_level"] == "high_risk"
        assert result["event_judgment"] == "risk_event"
        assert result["recommended_action"] in {"emergency_review", "expert_review"}

    def test_empty_input(self):
        result = parse_judge_output("")
        assert result["risk_level"] == "low_risk"
        assert result["event_judgment"] == "not_risk_event"
        assert result["recommended_action"] == "information_reply"

    def test_garbage_input(self):
        result = parse_judge_output("completely random garbage text 12345")
        assert result["risk_level"] == "low_risk"
        assert result["event_judgment"] == "not_risk_event"
        assert result["recommended_action"] == "information_reply"

    def test_partial_json(self):
        text = '{"risk_level": "mid_risk", "event_judgment": "risk_event"'
        result = parse_judge_output(text)
        assert result["risk_level"] == "mid_risk"
        assert result["event_judgment"] == "risk_event"

    def test_validation_correction_emergency_without_high(self):
        text = (
            '{"risk_level": "mid_risk", "event_topic": "无风险事件", "correlation_analysis": "", '
            '"event_judgment": "risk_event", "uncertainty_reason": "", '
            '"recommended_action": "emergency_review"}'
        )
        result = parse_judge_output(text)
        assert result["recommended_action"] == "expert_review"

    def test_not_risk_forces_safe_action(self):
        text = (
            '{"risk_level": "mid_risk", "event_topic": "无风险事件", "correlation_analysis": "", '
            '"event_judgment": "not_risk_event", "uncertainty_reason": "", '
            '"recommended_action": "create_work_order"}'
        )
        result = parse_judge_output(text)
        assert result["risk_level"] == "low_risk"
        assert result["recommended_action"] == "information_reply"
