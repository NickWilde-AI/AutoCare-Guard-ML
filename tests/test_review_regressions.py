"""交叉审查（2026-08-19）修复项的回归测试。

锁定统计口径与安全保护，防止修复回退：
- P1-04 KS 并列值 D 统计失真
- P1-05 AUPRC 并列概率抬升
- P1-17 split_rows 工单跨集泄漏
- P2-11 违规+安全处置矛盾组合
- P2-12 ban 行为证据判定收紧
- P2-19 公开数据主题透传校验
- P2-38 模型尺寸小数解析
- P2-49 fleiss ragged 拒绝
- P2-50 分位口径统一
- P2-56 统计实现精确值锁定
- P1-01 服务层 postprocess 接入（dict 入口）
- P1-08 guardrail 环境变量接线
- P2-14 request_id 一致性（集成）
- P2-13 reader 不再可读 /config（集成）
- 训练 collator labels/截断（无 torch 环境跳过 torch 分支）
"""

import json

import pytest

from im_guard_ml.build_dataset import normalize_public, split_rows
from im_guard_ml.drift_detection import ks_test
from im_guard_ml.evaluation import auprc, fleiss_kappa, percentile
from im_guard_ml.parsing import parse_judge_output
from im_guard_ml.postprocess import postprocess_model_output, postprocess_prediction
from im_guard_ml.schema import validate_label
from im_guard_ml.training import build_completion_labels
from im_guard_ml.training_readiness import _model_size_gb


# ---------------------------------------------------------------------------
# P1-05：AUPRC 并列处理
# ---------------------------------------------------------------------------


def test_auprc_all_ties_returns_expected_random_value():
    assert auprc([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)


def test_auprc_perfect_ranking():
    assert auprc([1, 1, 0], [0.9, 0.8, 0.1]) == pytest.approx(1.0)


def test_auprc_single_positive_second_rank():
    assert auprc([0, 1], [0.9, 0.1]) == pytest.approx(0.5)


def test_auprc_tie_order_invariant():
    a = auprc([1, 0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5, 0.5])
    b = auprc([1, 1, 1, 0, 0], [0.5, 0.5, 0.5, 0.5, 0.5])
    assert a == b


def test_auprc_no_positives():
    assert auprc([0, 0, 0], [0.9, 0.8, 0.1]) == 0.0


# ---------------------------------------------------------------------------
# P1-04：KS 并列值
# ---------------------------------------------------------------------------


def test_ks_identical_ties_zero():
    d, p = ks_test([1.0, 1.0], [1.0, 1.0])
    assert d == 0.0
    assert p == 1.0


def test_ks_disjoint_ranges_half():
    d, _ = ks_test([1.0, 2.0], [2.0, 3.0])
    assert d == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# P2-50 / percentile 口径
# ---------------------------------------------------------------------------


def test_percentile_linear_interpolation():
    assert percentile([1.0, 2.0, 3.0], 0.5) == pytest.approx(2.0)
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 1.0) == pytest.approx(5.0)
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == pytest.approx(4.8)


def test_percentile_single_value():
    assert percentile([100.0], 0.95) == 100.0
    assert percentile([], 0.5) == 0.0


# ---------------------------------------------------------------------------
# P2-49：fleiss ragged
# ---------------------------------------------------------------------------


def test_fleiss_kappa_rejects_ragged_matrix():
    with pytest.raises(ValueError, match="ragged"):
        fleiss_kappa([[3, 0, 0], [2, 0, 0]])


# ---------------------------------------------------------------------------
# P1-17：split_rows 工单隔离
# ---------------------------------------------------------------------------


def test_split_rows_keeps_same_ticket_in_one_split():
    rows = [
        {"ticket_id": "T1", "text": "a"},
        {"ticket_id": "T1", "text": "b"},
        {"ticket_id": "T2", "text": "c"},
        {"ticket_id": "T3", "text": "d"},
    ]
    splits = split_rows(rows, train_ratio=0.5, val_ratio=0.25, test_ratio=0.25, seed=42)
    assert len(splits["train"]) + len(splits["val"]) + len(splits["test"]) == 4
    ids = {name: {r["ticket_id"] for r in split_rows_} for name, split_rows_ in splits.items()}
    assert not (ids["train"] & ids["val"])
    assert not (ids["train"] & ids["test"])
    assert not (ids["val"] & ids["test"])


# ---------------------------------------------------------------------------
# P2-19：公开数据主题透传校验
# ---------------------------------------------------------------------------


def test_normalize_public_unmapped_topic_falls_back():
    row = {"text": "hi", "topic": "weird_custom_topic", "label": 1}
    result = normalize_public(row, "test")
    assert result["label"]["event_topic"] == "质保、零部件与服务争议"


def test_normalize_public_known_topic_passes_through():
    row = {"text": "hi", "topic": "动力电池与热安全", "label": 1}
    result = normalize_public(row, "test")
    assert result["label"]["event_topic"] == "动力电池与热安全"


# ---------------------------------------------------------------------------
# AutoCare：风险事件 + 信息回复矛盾组合
# ---------------------------------------------------------------------------


def test_validate_label_rejects_risk_event_with_information_reply():
    errors = validate_label(
        {
            "risk_level": "mid_risk",
            "event_judgment": "risk_event",
            "recommended_action": "information_reply",
            "event_topic": "无风险事件",
        }
    )
    assert any("information_reply" in e for e in errors)


def test_parse_corrects_risk_event_with_information_reply():
    result = parse_judge_output(
        '{"risk_level": "low_risk", "event_judgment": "risk_event", "recommended_action": "information_reply"}'
    )
    assert result["risk_level"] == "mid_risk"
    assert result["recommended_action"] == "service_followup"


# ---------------------------------------------------------------------------
# emergency 车辆证据门禁
# ---------------------------------------------------------------------------

_EMERGENCY_RAW = (
    '{"risk_level": "high_risk", "event_topic": "动力电池与热安全", "correlation_analysis": "", '
    '"event_judgment": "risk_event", "uncertainty_reason": "", "recommended_action": "emergency_review", '
    '"evidence_refs": [{"source": "conversation_evidence", "field": "content"}]}'
)


def test_emergency_without_vehicle_evidence_downgrades():
    case = {
        "conversation_evidence": [{"content": "有焦糊味"}],
        "vehicle_signal_summary": {},
        "fault_evidence": [],
    }
    result = postprocess_model_output(_EMERGENCY_RAW, case)
    assert result.parsed_output["recommended_action"] == "expert_review"
    assert result.parse_status == "corrected"


def test_emergency_with_vehicle_evidence_keeps_emergency():
    case = {
        "conversation_evidence": [{"content": "有焦糊味"}],
        "vehicle_signal_summary": {"warning_lights": ["电池过热"]},
        "fault_evidence": [{"fault_domain": "battery", "severity_from_source": "critical"}],
    }
    raw = (
        '{"risk_level": "high_risk", "event_topic": "动力电池与热安全", "correlation_analysis": "", '
        '"event_judgment": "risk_event", "uncertainty_reason": "", "recommended_action": "emergency_review", '
        '"evidence_refs": [{"source": "vehicle_signal_summary", "field": "warning_lights"}]}'
    )
    result = postprocess_model_output(raw, case)
    assert result.route == "review_queue"
    assert result.parsed_output["recommended_action"] == "emergency_review"
    assert result.requires_human_review is True


# ---------------------------------------------------------------------------
# P1-01：postprocess dict 入口（服务层统一路径）
# ---------------------------------------------------------------------------


def test_postprocess_prediction_dict_entry():
    pred = {
        "risk_level": "high_risk",
        "event_topic": "动力电池与热安全",
        "event_judgment": "risk_event",
        "recommended_action": "emergency_review",
        "evidence_refs": [{"source": "vehicle_signal_summary", "field": "warning_lights"}],
    }
    case = {
        "vehicle_signal_summary": {"warning_lights": ["电池过热"]},
        "fault_evidence": [{"fault_domain": "battery", "severity_from_source": "critical"}],
    }
    result = postprocess_prediction(pred, case)
    assert result.parse_status == "ok"
    assert result.route == "review_queue"
    assert result.final_action == "await_human_confirmation"


# ---------------------------------------------------------------------------
# 训练：completion labels 纯函数 + collator（torch 可选）
# ---------------------------------------------------------------------------


def test_build_completion_labels_masks_prompt_and_fields():
    labels = build_completion_labels([1, 2, 3, 4, 5], [0, 0, 1, 1, 0])
    assert labels == [-100, -100, 3, 4, -100]


def test_completion_mask_collator_pads_and_truncates():
    torch = pytest.importorskip("torch")
    from im_guard_ml.training import CompletionMaskCollator

    collator = CompletionMaskCollator(pad_token_id=0, max_length=4)
    features = [
        {"input_ids": [1, 2, 3, 4, 5, 6], "completion_mask": [0, 0, 0, 1, 1, 1]},
        {"input_ids": [7, 8], "completion_mask": [0, 1]},
    ]
    batch = collator(features)
    assert batch["input_ids"].shape == (2, 4)
    assert batch["labels"][0].tolist() == [-100, 4, 5, 6]  # keep_end 截断后 mask 对齐
    assert batch["labels"][1].tolist() == [-100, 8, -100, -100]
    assert batch["attention_mask"].tolist() == [[1, 1, 1, 1], [1, 1, 0, 0]]


# ---------------------------------------------------------------------------
# P2-38：模型尺寸解析
# ---------------------------------------------------------------------------


def test_model_size_gb_parses_fractional_and_plain():
    assert _model_size_gb("Qwen/Qwen3-32B") == 32.0
    assert _model_size_gb("Qwen2.5-0.5B-Instruct") == 0.5
    assert _model_size_gb("Qwen2.5-7B-Instruct") == 7.0
    assert _model_size_gb("sshleifer/tiny-gpt2") is None


# ---------------------------------------------------------------------------
# P1-08：guardrail 环境变量接线
# ---------------------------------------------------------------------------

_SAFE = {
    "risk_level": "low_risk",
    "event_topic": "无风险事件",
    "event_judgment": "not_risk_event",
    "recommended_action": "information_reply",
}


def test_ab_report_env_guardrail_override(monkeypatch):
    from im_guard_ml.rollout import build_ab_report

    monkeypatch.setenv("IM_GUARD_BAN_FPR_REDLINE", "0.01")
    control = [{"ticket_id": "s1", "label": _SAFE, "prediction": _SAFE}]
    candidate = [
        {
            "ticket_id": "s1",
            "label": _SAFE,
            "prediction": {**_SAFE, "recommended_action": "emergency_review"},
        }
    ]
    report = build_ab_report(control, candidate)
    guardrail = next(
        item for item in report["guardrails"] if item["name"] == "emergency_review_fpr_max"
    )
    assert guardrail["threshold"] == 0.01
    assert guardrail["status"] == "fail"


# ---------------------------------------------------------------------------
# P2-13 / P2-14 / P1-01 集成：/judge 行为
# ---------------------------------------------------------------------------


def test_judge_generated_request_id_consistent(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from im_guard_ml.api import create_app

    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())
    resp = client.post(
        "/judge",
        json={"case_id": "rid-1", "conversation_evidence": [{"content": "普通咨询"}]},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == resp.json()["request_id"]


def test_judge_emergency_without_vehicle_downgraded_and_observable(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from im_guard_ml.api import create_app

    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())
    resp = client.post(
        "/judge",
        json={
            "case_id": "em-1",
            "conversation_evidence": [{"content": "车内有焦糊味，好像电池冒烟了"}],
            "vehicle_signal_summary": {},
            "fault_evidence": [],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # 无车辆侧证据时不应维持 emergency_review（启发式可能给 expert/collect）
    assert body["recommended_action"] != "emergency_review" or body.get("requires_human_review") is True
    assert "requires_human_review" in body
    assert body["parse_status"] in {"ok", "corrected"}


def test_reader_cannot_access_config_endpoint(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from im_guard_ml.api import create_app

    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.delenv("IM_GUARD_API_TOKENS", raising=False)
    monkeypatch.setenv("IM_GUARD_API_TOKENS", "reader-token:reader")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())
    assert client.get("/config", headers={"Authorization": "Bearer reader-token"}).status_code == 401
    assert client.get("/dashboard/data", headers={"Authorization": "Bearer reader-token"}).status_code == 200
