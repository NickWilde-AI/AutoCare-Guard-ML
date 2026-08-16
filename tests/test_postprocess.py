"""Tests for postprocessing and routing logic."""

import pytest

from im_guard_ml.postprocess import postprocess_model_output, route_policy, PostprocessResult


class TestRoutePolicy:
    def test_ignore_routes_to_auto_close(self):
        label = {"handling_suggestion": "ignore"}
        route, action = route_policy(label)
        assert route == "auto_close"
        assert action == "ignore"

    def test_warning_routes_to_auto_action(self):
        label = {"handling_suggestion": "warning"}
        route, action = route_policy(label)
        assert route == "auto_action"
        assert action == "send_warning"

    def test_limit_routes_to_policy_action(self):
        label = {"handling_suggestion": "limit_account"}
        route, action = route_policy(label)
        assert route == "policy_action"
        assert action == "limit_account_candidate"

    def test_ban_routes_to_human_review(self):
        label = {"handling_suggestion": "ban_account"}
        route, action = route_policy(label)
        assert route == "human_review_required"
        assert action == "review_before_ban"

    def test_unknown_routes_to_fallback(self):
        label = {"handling_suggestion": "unknown_value"}
        route, action = route_policy(label)
        assert route == "fallback_or_review"
        assert action == "defer_to_rule_engine"

    def test_errors_with_ban_routes_to_human_review(self):
        label = {"handling_suggestion": "ban_account"}
        route, action = route_policy(label, errors=["some error"])
        assert route == "human_review_required"

    def test_errors_without_ban_routes_to_fallback(self):
        label = {"handling_suggestion": "warning"}
        route, action = route_policy(label, errors=["some error"])
        assert route == "fallback_or_review"


class TestPostprocessModelOutput:
    def test_valid_high_risk_ban(self):
        raw = '{"risk_level": "high_risk", "topic": "代刷/包榜", "correlation_analysis": "test", "final_judgment": "exist_violation", "judgment_basis": "test", "handling_suggestion": "ban_account"}'
        case = {
            "audit_scene": {
                "behavior_key_summary": {
                    "gift_total_value": 10000,
                    "reward_behavior": "持续高频大额打赏。",
                }
            },
            "behavior_abnormal_list": [{"abnormal_type": "大额打赏"}],
        }
        result = postprocess_model_output(raw, case)
        assert result.route == "human_review_required"
        assert result.final_action == "review_before_ban"
        assert result.parse_status == "ok"

    def test_ban_without_behavior_downgrades(self):
        raw = '{"risk_level": "high_risk", "topic": "代刷/包榜", "correlation_analysis": "test", "final_judgment": "exist_violation", "judgment_basis": "test", "handling_suggestion": "ban_account"}'
        case = {
            "audit_scene": {"behavior_key_summary": {}},
            "behavior_abnormal_list": [],
        }
        result = postprocess_model_output(raw, case)
        # Should downgrade to limit_account due to missing behavior evidence
        assert result.parsed_output["handling_suggestion"] == "limit_account"
        # Route goes to fallback because there were validation errors
        assert result.parse_status == "corrected"
        assert "behavior evidence missing" in result.validation_errors[0]

    def test_safe_prediction(self):
        raw = '{"risk_level": "low_risk", "topic": "无主题", "correlation_analysis": "", "final_judgment": "not_exist_violation", "judgment_basis": "", "handling_suggestion": "ignore"}'
        case = {
            "audit_scene": {"behavior_key_summary": {}},
            "behavior_abnormal_list": [],
        }
        result = postprocess_model_output(raw, case)
        assert result.route == "auto_close"
        assert result.parse_status == "ok"

    def test_parse_failure_defaults_safe(self):
        raw = "completely broken output"
        case = {
            "audit_scene": {"behavior_key_summary": {}},
            "behavior_abnormal_list": [],
        }
        result = postprocess_model_output(raw, case)
        assert result.parsed_output["final_judgment"] == "not_exist_violation"
        assert result.route == "auto_close"

    def test_to_dict(self):
        raw = '{"risk_level": "low_risk", "topic": "无主题", "correlation_analysis": "", "final_judgment": "not_exist_violation", "judgment_basis": "", "handling_suggestion": "ignore"}'
        result = postprocess_model_output(raw, {})
        d = result.to_dict()
        assert "route" in d
        assert "parse_status" in d
        assert "risk_level" in d
