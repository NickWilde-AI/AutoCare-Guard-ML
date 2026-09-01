from autocare_guard_ml.data_audit import audit_dataset, detect_pii_types


def test_detect_pii_types_finds_email_phone_and_id_card():
    row = {
        "case_id": "pii-1",
        "service_context": {},
        "conversation_evidence": [
            {"content": "邮箱 a@example.com 手机 13800138000 身份证 110101199003077771"}
        ],
        "vehicle_signal_summary": {},
        "fault_evidence": [],
        "label": {
            "risk_level": "low_risk",
            "event_topic": "无风险事件",
            "event_judgment": "not_risk_event",
            "recommended_action": "information_reply",
        },
    }

    assert set(detect_pii_types(row)) == {"email", "phone_cn", "id_card_cn"}
    report = audit_dataset([row])
    assert report["pii_risk_count"] == 3
    assert report["pii_risk_by_type"]["email"] == 1


def _case(
    case_id,
    *,
    source="internal_history",
    task_type=None,
    risk_level="low_risk",
    topic="无风险事件",
    judgment="not_risk_event",
    action="information_reply",
):
    row = {
        "case_id": case_id,
        "ticket_id": case_id,
        "service_context": {},
        "conversation_evidence": [{"content": f"普通咨询 {case_id}"}],
        "vehicle_signal_summary": {},
        "fault_evidence": [],
        "source": source,
        "label": {
            "risk_level": risk_level,
            "event_topic": topic,
            "event_judgment": judgment,
            "recommended_action": action,
        },
    }
    if task_type is not None:
        row["task_type"] = task_type
    return row


def test_audit_dataset_reports_source_type_and_label_distributions():
    rows = [
        _case("internal-1", source="internal_history"),
        _case(
            "public-1",
            source="xguard_train_open_200k",
            task_type="public_binary",
            risk_level="mid_risk",
            judgment="risk_event",
            action="service_followup",
        ),
        _case(
            "synthetic-1",
            source="level_generator_high",
            risk_level="high_risk",
            topic="充电与高压系统异常",
            judgment="risk_event",
            action="emergency_review",
        ),
        _case(
            "hard-1",
            source="refinement_hard",
            risk_level="mid_risk",
            topic="充电与高压系统异常",
            judgment="risk_event",
            action="service_followup",
        ),
    ]

    report = audit_dataset(rows)

    assert report["by_source_type"] == {
        "hard_case": 1,
        "internal": 1,
        "public_binary": 1,
        "synthetic": 1,
    }
    assert report["by_risk_level"]["high_risk"] == 1
    action_dist = report.get("by_recommended_action") or report.get("by_handling_suggestion")
    assert action_dist["service_followup"] == 2
    assert report["quality_status"] == "pass"


def test_audit_dataset_warns_when_large_dataset_is_severely_imbalanced():
    rows = [_case(f"safe-{idx}") for idx in range(20)]

    report = audit_dataset(rows)

    assert report["quality_status"] == "pass"
    warning_fields = {item["field"] for item in report["distribution_warnings"]}
    assert warning_fields & {"event_judgment", "final_judgment", "recommended_action", "handling_suggestion"}
