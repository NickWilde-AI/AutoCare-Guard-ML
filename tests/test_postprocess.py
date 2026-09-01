"""Tests for AutoCare postprocessing and routing logic."""

from im_guard_ml.postprocess import postprocess_model_output, route_policy


class TestRoutePolicy:
    def test_information_reply_routes(self):
        label = {"recommended_action": "information_reply"}
        route, action, requires_human, *_ = route_policy(label)
        assert route == "information_flow"
        assert action == "information_reply_candidate"
        assert requires_human is False

    def test_collect_evidence_routes(self):
        label = {"recommended_action": "collect_more_evidence"}
        route, action, requires_human, *_ = route_policy(label)
        assert route == "collect_evidence"
        assert action == "request_more_evidence"
        assert requires_human is False

    def test_work_order_routes(self):
        label = {"recommended_action": "create_work_order"}
        route, action, *_ = route_policy(label)
        assert route == "work_order_queue"
        assert action == "create_work_order_candidate"

    def test_emergency_routes_to_review(self):
        label = {"recommended_action": "emergency_review"}
        route, action, requires_human, role, priority, _ = route_policy(label)
        assert route == "review_queue"
        assert action == "await_human_confirmation"
        assert requires_human is True
        assert role == "safety_reviewer"
        assert priority == "urgent"

    def test_unknown_routes_to_fallback(self):
        label = {"recommended_action": "unknown_value"}
        route, action, requires_human, *_ = route_policy(label)
        assert route == "fallback_or_review"
        assert action == "defer_to_rule_engine"
        assert requires_human is True

    def test_errors_with_emergency_stay_in_review(self):
        label = {"recommended_action": "emergency_review"}
        route, action, requires_human, *_ = route_policy(label, errors=["some error"])
        assert route == "review_queue"
        assert requires_human is True

    def test_errors_without_emergency_routes_to_fallback(self):
        label = {"recommended_action": "service_followup"}
        route, *_ = route_policy(label, errors=["some error"])
        assert route == "fallback_or_review"


class TestPostprocessModelOutput:
    def test_valid_high_risk_emergency(self):
        raw = (
            '{"risk_level": "high_risk", "event_topic": "动力电池与热安全", '
            '"correlation_analysis": "test", "event_judgment": "risk_event", '
            '"uncertainty_reason": "test", "recommended_action": "emergency_review", '
            '"evidence_refs": [{"source": "vehicle_signal_summary", "field": "warning_lights"}]}'
        )
        case = {
            "vehicle_signal_summary": {"warning_lights": ["电池过热"]},
            "conversation_evidence": [{"content": "有焦糊味"}],
            "fault_evidence": [{"fault_domain": "battery", "severity_from_source": "critical"}],
        }
        result = postprocess_model_output(raw, case)
        assert result.route == "review_queue"
        assert result.final_action == "await_human_confirmation"
        assert result.requires_human_review is True
        assert result.parse_status == "ok"

    def test_emergency_without_vehicle_evidence_downgrades(self):
        # 故意不含 index，避免 parse 阶段因无 case 上下文误判 evidence_refs
        raw = (
            '{"risk_level": "high_risk", "event_topic": "动力电池与热安全", '
            '"correlation_analysis": "test", "event_judgment": "risk_event", '
            '"uncertainty_reason": "test", "recommended_action": "emergency_review", '
            '"evidence_refs": [{"source": "conversation_evidence", "field": "content"}]}'
        )
        case = {
            "vehicle_signal_summary": {},
            "conversation_evidence": [{"content": "有焦糊味"}],
            "fault_evidence": [],
        }
        result = postprocess_model_output(raw, case)
        assert result.parsed_output["recommended_action"] == "expert_review"
        assert result.parse_status == "corrected"
        assert any("vehicle-side evidence missing" in e for e in result.validation_errors)

    def test_safe_prediction(self):
        raw = (
            '{"risk_level": "low_risk", "event_topic": "无风险事件", "correlation_analysis": "", '
            '"event_judgment": "not_risk_event", "uncertainty_reason": "", '
            '"recommended_action": "information_reply"}'
        )
        case = {"vehicle_signal_summary": {}, "conversation_evidence": [], "fault_evidence": []}
        result = postprocess_model_output(raw, case)
        assert result.route == "information_flow"
        assert result.parse_status == "ok"

    def test_parse_failure_defaults_safe(self):
        raw = "completely broken output"
        case = {"vehicle_signal_summary": {}, "conversation_evidence": [], "fault_evidence": []}
        result = postprocess_model_output(raw, case)
        assert result.parsed_output["event_judgment"] == "not_risk_event"
        assert result.route == "information_flow"

    def test_to_dict(self):
        raw = (
            '{"risk_level": "low_risk", "event_topic": "无风险事件", "correlation_analysis": "", '
            '"event_judgment": "not_risk_event", "uncertainty_reason": "", '
            '"recommended_action": "information_reply"}'
        )
        result = postprocess_model_output(raw, {})
        d = result.to_dict()
        assert "route" in d
        assert "parse_status" in d
        assert "requires_human_review" in d
        assert "risk_level" in d
