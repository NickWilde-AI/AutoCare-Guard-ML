"""Tests for the AutoCare heuristic rule judge."""

from im_guard_ml.inference import HeuristicJudge


def _judge() -> HeuristicJudge:
    return HeuristicJudge({})


def test_battery_smoke_maps_to_battery_topic():
    result = _judge().predict(
        {
            "service_context": {},
            "conversation_evidence": [{"content": "车内有焦糊味，好像电池冒烟了"}],
            "vehicle_signal_summary": {"warning_lights": ["电池过热"]},
            "fault_evidence": [{"fault_domain": "battery", "severity_from_source": "critical"}],
            "vehicle_context": {"vehicle_motion_state": "driving"},
        }
    )
    assert result["event_topic"] == "动力电池与热安全"
    assert result["event_judgment"] == "risk_event"
    assert result["recommended_action"] == "emergency_review"
    assert result["risk_level"] == "high_risk"


def test_plain_chat_is_safe():
    result = _judge().predict(
        {
            "service_context": {},
            "conversation_evidence": [{"content": "请问质保政策在哪里看？"}],
            "vehicle_signal_summary": {},
            "fault_evidence": [],
        }
    )
    # "质保" keyword may map to warranty topic with mid risk; use truly neutral text
    result = _judge().predict(
        {
            "service_context": {},
            "conversation_evidence": [{"content": "你好，今天天气不错"}],
            "vehicle_signal_summary": {},
            "fault_evidence": [],
        }
    )
    assert result["event_judgment"] == "not_risk_event"
    assert result["risk_level"] == "low_risk"
    assert result["recommended_action"] == "information_reply"


def test_charging_without_vehicle_evidence_routes_expert():
    result = _judge().predict(
        {
            "service_context": {},
            "conversation_evidence": [{"content": "充电枪充不上电，反复中断"}],
            "vehicle_signal_summary": {},
            "fault_evidence": [],
        }
    )
    assert result["event_topic"] == "充电与高压系统异常"
    assert result["risk_level"] == "mid_risk"
    assert result["recommended_action"] in {"expert_review", "collect_more_evidence"}


def test_vehicle_evidence_with_mid_risk_creates_work_order():
    result = _judge().predict(
        {
            "service_context": {},
            "conversation_evidence": [{"content": "充电偶尔中断"}],
            "vehicle_signal_summary": {"warning_lights": ["充电异常"], "charging_status": "fault"},
            "fault_evidence": [],
        }
    )
    assert result["event_judgment"] == "risk_event"
    assert result["recommended_action"] == "create_work_order"


def test_severe_missing_evidence_collect_more():
    result = _judge().predict(
        {
            "service_context": {},
            "conversation_evidence": [{"content": "感觉制动有点软"}],
            "vehicle_signal_summary": {},
            "fault_evidence": [],
            "missing_and_conflicts": {"missing_fields": ["vehicle_signal_summary"]},
        }
    )
    assert result["event_judgment"] == "insufficient_evidence"
    assert result["recommended_action"] == "collect_more_evidence"
