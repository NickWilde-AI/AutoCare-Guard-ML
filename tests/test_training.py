"""Tests for training module (field-level loss masking)."""

from im_guard_ml.training import _normalize_public_binary_labels, FieldLevelMaskCollator, tokenize_training_case


class TestNormalizePublicBinaryLabels:
    def test_internal_data_unchanged(self):
        case = {
            "task_type": "multi_label",
            "label": {
                "risk_level": "high_risk",
                "final_judgment": "exist_violation",
                "handling_suggestion": "ban_account",
                "topic": "代刷/包榜",
            },
        }
        result = _normalize_public_binary_labels(case)
        assert result["label"]["risk_level"] == "high_risk"
        assert result["label"]["handling_suggestion"] == "ban_account"

    def test_public_violation_capped(self):
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
        assert result["label"]["handling_suggestion"] == "warning"

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
        assert result["label"]["handling_suggestion"] == "ignore"
        assert result["label"]["topic"] == "无主题"

    def test_no_label_unchanged(self):
        case = {"task_type": "public_binary", "label": "not_a_dict"}
        result = _normalize_public_binary_labels(case)
        assert result["label"] == "not_a_dict"

    def test_missing_task_type_unchanged(self):
        case = {
            "label": {
                "risk_level": "high_risk",
                "final_judgment": "exist_violation",
                "handling_suggestion": "ban_account",
            },
        }
        result = _normalize_public_binary_labels(case)
        assert result["label"]["handling_suggestion"] == "ban_account"


class ToyTokenizer:
    pad_token_id = 0

    def encode(self, text, add_special_tokens=False):
        return [ord(ch) for ch in text]

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        body = {"input_ids": [ord(ch) for ch in text]}
        if return_offsets_mapping:
            body["offset_mapping"] = [(i, i + 1) for i in range(len(text))]
        return body


def test_tokenize_public_binary_masks_public_risk_and_handling_fields():
    case = _normalize_public_binary_labels(
        {
            "task_type": "public_binary",
            "audit_scene": {},
            "chat_evidence_list": [],
            "behavior_abnormal_list": [],
            "label": {
                "risk_level": "high_risk",
                "final_judgment": "exist_violation",
                "handling_suggestion": "ban_account",
                "topic": "诈骗引流",
            },
        }
    )

    tokenized = tokenize_training_case(case, tokenizer=ToyTokenizer(), rubrics={}, enable_field_mask=True)
    text = "".join(chr(i) for i in tokenized["input_ids"])
    risk_start = text.rindex('"risk_level"')
    handling_start = text.rindex('"handling_suggestion"')
    final_start = text.rindex('"final_judgment"')

    assert tokenized["completion_mask"][risk_start] == 0
    assert tokenized["completion_mask"][handling_start] == 0
    assert tokenized["completion_mask"][final_start] == 1
