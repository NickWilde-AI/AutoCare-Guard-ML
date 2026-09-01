from im_guard_ml.privacy import build_input_summary, redact_text


def test_redact_text_masks_common_pii():
    redacted, pii_types = redact_text("邮箱 a@example.com 手机 13800138000 身份证 110101199003077771")

    assert "a@example.com" not in redacted
    assert "13800138000" not in redacted
    assert "110101199003077771" not in redacted
    assert set(pii_types) == {"email", "phone_cn", "id_card_cn"}


def test_build_input_summary_keeps_counts_hash_and_redacted_samples():
    case = {
        "case_id": "t1",
        "conversation_evidence": [{"content": "联系 a@example.com"}],
        "fault_evidence": [{"fault_domain": "battery"}],
        "hint_topic": "动力电池与热安全",
    }

    summary = build_input_summary(case)

    assert summary["conversation_evidence_count"] == 1
    assert summary["fault_evidence_count"] == 1
    assert summary["chat_evidence_count"] == 1  # 兼容字段
    assert summary["hint_topic"] == "动力电池与热安全"
    assert summary["pii_types"] == ["email"]
    assert "a@example.com" not in summary["redacted_evidence_samples"][0]
    assert len(summary["payload_sha256"]) == 64
