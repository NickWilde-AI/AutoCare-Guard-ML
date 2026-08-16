from im_guard_ml.data_audit import audit_dataset, detect_pii_types


def test_detect_pii_types_finds_email_phone_and_id_card():
    row = {
        "ticket_id": "pii-1",
        "audit_scene": {},
        "chat_evidence_list": [{"original_content": "邮箱 a@example.com 手机 13800138000 身份证 110101199003077771"}],
        "behavior_abnormal_list": [],
        "label": {
            "risk_level": "low_risk",
            "topic": "无主题",
            "final_judgment": "not_exist_violation",
            "handling_suggestion": "ignore",
        },
    }

    assert set(detect_pii_types(row)) == {"email", "phone_cn", "id_card_cn"}
    report = audit_dataset([row])
    assert report["pii_risk_count"] == 3
    assert report["pii_risk_by_type"]["email"] == 1


def _case(ticket_id, *, source="internal_history", task_type=None, risk_level="low_risk", topic="无主题", judgment="not_exist_violation", handling="ignore"):
    row = {
        "ticket_id": ticket_id,
        "audit_scene": {},
        "chat_evidence_list": [f"普通聊天 {ticket_id}"],
        "behavior_abnormal_list": [],
        "source": source,
        "label": {
            "risk_level": risk_level,
            "topic": topic,
            "final_judgment": judgment,
            "handling_suggestion": handling,
        },
    }
    if task_type is not None:
        row["task_type"] = task_type
    return row


def test_audit_dataset_reports_source_type_and_label_distributions():
    rows = [
        _case("internal-1", source="internal_history"),
        _case("public-1", source="xguard_train_open_200k", task_type="public_binary", risk_level="mid_risk", judgment="exist_violation", handling="warning"),
        _case("synthetic-1", source="level_generator_high", risk_level="high_risk", topic="诈骗引流", judgment="exist_violation", handling="ban_account"),
        _case("hard-1", source="refinement_hard", risk_level="mid_risk", topic="诈骗引流", judgment="exist_violation", handling="warning"),
    ]

    report = audit_dataset(rows)

    assert report["by_source_type"] == {
        "hard_case": 1,
        "internal": 1,
        "public_binary": 1,
        "synthetic": 1,
    }
    assert report["by_risk_level"]["high_risk"] == 1
    assert report["by_handling_suggestion"]["warning"] == 2
    assert report["quality_status"] == "pass"


def test_audit_dataset_warns_when_large_dataset_is_severely_imbalanced():
    rows = [_case(f"safe-{idx}") for idx in range(20)]

    report = audit_dataset(rows)

    assert report["quality_status"] == "pass"
    assert any(item["field"] == "final_judgment" for item in report["distribution_warnings"])
    assert any(item["field"] == "handling_suggestion" for item in report["distribution_warnings"])
