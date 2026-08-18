"""Tests for the heuristic rule judge (P2-25 覆盖缺口：inference 模块此前零测试)."""

from im_guard_ml.inference import HeuristicJudge


def _judge() -> HeuristicJudge:
    return HeuristicJudge({})


def test_gamble_chat_maps_to_fraud_topic():
    # 定稿口径：11 类一级主题，赌博/博彩引流归入"诈骗引流"。
    result = _judge().predict(
        {
            "audit_scene": {},
            "chat_evidence_list": [{"original_content": "加群看走势图，跟着计划买，稳赢不亏"}],
            "behavior_abnormal_list": [],
        }
    )
    assert result["topic"] == "诈骗引流"
    assert result["final_judgment"] == "exist_violation"


def test_plain_chat_is_safe():
    result = _judge().predict(
        {
            "audit_scene": {},
            "chat_evidence_list": [{"original_content": "今天天气不错，周末一起开黑吗？"}],
            "behavior_abnormal_list": [],
        }
    )
    assert result["final_judgment"] == "not_exist_violation"
    assert result["risk_level"] == "low_risk"
    assert result["handling_suggestion"] == "ignore"


def test_semantic_only_mid_risk_routes_warning():
    # 仅语义命中、无行为/大额印证 → 轻度首次风险走 warning（P2-21）。
    result = _judge().predict(
        {
            "audit_scene": {"behavior_key_summary": {}},
            "chat_evidence_list": [{"original_content": "加我私V，发你一个稳赚的项目"}],
            "behavior_abnormal_list": [],
        }
    )
    assert result["risk_level"] == "mid_risk"
    assert result["handling_suggestion"] == "warning"


def test_behavior_only_violation_basis_does_not_claim_semantic_hit():
    # 纯行为触发（无语义命中）时，依据不得声称"命中违规语义要点"（P2-21）。
    result = _judge().predict(
        {
            "audit_scene": {
                "behavior_key_summary": {
                    "gift_total_value": 6000,
                    "t_bean_consume": "大额消费。",
                    "reward_behavior": "持续高频大额打赏。",
                }
            },
            "chat_evidence_list": [{"original_content": "你好，在吗？"}],
            "behavior_abnormal_list": [{"abnormal_type": "异常打赏模式"}],
        }
    )
    assert result["final_judgment"] == "exist_violation"
    assert "未识别到明确违规话术" in result["judgment_basis"]
    assert "命中违规语义要点" not in result["judgment_basis"]


def test_brush_with_behavior_confirmation_is_high_ban():
    result = _judge().predict(
        {
            "audit_scene": {},
            "chat_evidence_list": [{"original_content": "今晚还是老规矩，帮我冲一下。"}],
            "behavior_abnormal_list": [{"abnormal_type": "短时高频大额打赏"}],
        }
    )
    assert result["risk_level"] == "high_risk"
    assert result["handling_suggestion"] == "ban_account"
    assert result["topic"] == "代刷/包榜"
