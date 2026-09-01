"""Tests for training module (field-level loss masking, AutoCare)."""

from im_guard_ml.training import _normalize_public_binary_labels, tokenize_training_case


class TestNormalizePublicBinaryLabels:
    def test_internal_data_unchanged(self):
        case = {
            "task_type": "multi_label",
            "label": {
                "risk_level": "high_risk",
                "event_judgment": "risk_event",
                "recommended_action": "emergency_review",
                "event_topic": "动力电池与热安全",
            },
        }
        result = _normalize_public_binary_labels(case)
        assert result["label"]["risk_level"] == "high_risk"
        assert result["label"]["recommended_action"] == "emergency_review"

    def test_public_risk_capped(self):
        case = {
            "task_type": "public_binary",
            "label": {
                "risk_level": "high_risk",
                "final_judgment": "exist_violation",
                "handling_suggestion": "ban_account",
                "topic": "辱骂攻击",
            },
        }
        result = _normalize_public_binary_labels(case)
        assert result["label"]["risk_level"] == "mid_risk"
        assert result["label"]["recommended_action"] == "service_followup"
        assert result["label"]["event_judgment"] == "risk_event"

    def test_public_safe_normalized(self):
        case = {
            "task_type": "public_binary",
            "label": {
                "risk_level": "mid_risk",
                "final_judgment": "not_exist_violation",
                "handling_suggestion": "warning",
                "topic": "辱骂攻击",
            },
        }
        result = _normalize_public_binary_labels(case)
        assert result["label"]["risk_level"] == "low_risk"
        assert result["label"]["recommended_action"] == "information_reply"
        assert result["label"]["event_topic"] == "无风险事件"

    def test_no_label_unchanged(self):
        case = {"task_type": "public_binary", "label": "not_a_dict"}
        result = _normalize_public_binary_labels(case)
        assert result["label"] == "not_a_dict"

    def test_missing_task_type_unchanged(self):
        case = {
            "label": {
                "risk_level": "high_risk",
                "recommended_action": "emergency_review",
            },
        }
        result = _normalize_public_binary_labels(case)
        assert result["label"]["recommended_action"] == "emergency_review"


class ToyTokenizer:
    pad_token_id = 0

    def encode(self, text, add_special_tokens=False):
        return [ord(ch) for ch in text]

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        body = {"input_ids": [ord(ch) for ch in text]}
        if return_offsets_mapping:
            body["offset_mapping"] = [(i, i + 1) for i in range(len(text))]
        return body


def test_tokenize_public_binary_masks_risk_topic_and_action_fields():
    case = _normalize_public_binary_labels(
        {
            "task_type": "public_binary",
            "service_context": {},
            "conversation_evidence": [],
            "fault_evidence": [],
            "label": {
                "risk_level": "high_risk",
                "final_judgment": "exist_violation",
                "handling_suggestion": "ban_account",
                "topic": "动力电池与热安全",
            },
        }
    )

    tokenized = tokenize_training_case(case, tokenizer=ToyTokenizer(), rubrics={}, enable_field_mask=True)
    text = "".join(chr(i) for i in tokenized["input_ids"])
    risk_start = text.rindex('"risk_level"')
    action_start = text.rindex('"recommended_action"')
    judgment_start = text.rindex('"event_judgment"')
    topic_start = text.rindex('"event_topic"')

    assert tokenized["completion_mask"][risk_start] == 0
    assert tokenized["completion_mask"][action_start] == 0
    assert tokenized["completion_mask"][topic_start] == 0
    assert tokenized["completion_mask"][judgment_start] == 1
