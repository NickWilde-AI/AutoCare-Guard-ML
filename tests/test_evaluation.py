"""Tests for evaluation metrics (AutoCare fields)."""

import pytest

from im_guard_ml.evaluation import (
    auprc,
    eval_binary,
    eval_multi_field,
    fleiss_kappa,
    macro_f1,
    ordinal_krippendorff_alpha,
)


class TestEvalBinary:
    def test_perfect_predictions(self):
        targets = [1, 1, 0, 0, 1, 0]
        preds = [1, 1, 0, 0, 1, 0]
        result = eval_binary(targets, preds)
        assert result["accuracy"] == 1.0
        assert result["f1"] == 1.0
        assert result["fpr"] == 0.0

    def test_all_wrong(self):
        targets = [1, 1, 0, 0]
        preds = [0, 0, 1, 1]
        result = eval_binary(targets, preds)
        assert result["accuracy"] == 0.0
        assert result["fpr"] == 1.0

    def test_with_probabilities(self):
        targets = [1, 1, 0, 1, 0]
        preds = [1, 0, 0, 1, 0]
        probs = [0.9, 0.4, 0.1, 0.8, 0.2]
        result = eval_binary(targets, preds, probs)
        assert result["auprc"] is not None
        assert 0.0 <= result["auprc"] <= 1.0

    def test_without_probabilities(self):
        targets = [1, 0, 1]
        preds = [1, 0, 0]
        result = eval_binary(targets, preds)
        assert result["auprc"] is None


class TestMacroF1:
    def test_perfect_predictions(self):
        targets = ["a", "b", "c", "a", "b", "c"]
        preds = ["a", "b", "c", "a", "b", "c"]
        labels = ["a", "b", "c"]
        assert macro_f1(targets, preds, labels) == 1.0

    def test_partial_correct(self):
        targets = ["a", "a", "b", "b"]
        preds = ["a", "b", "b", "a"]
        labels = ["a", "b"]
        result = macro_f1(targets, preds, labels)
        assert 0.0 < result < 1.0


class TestEvalMultiField:
    def test_basic_evaluation(self):
        targets = [
            {
                "risk_level": "high_risk",
                "recommended_action": "emergency_review",
                "event_judgment": "risk_event",
            },
            {
                "risk_level": "low_risk",
                "recommended_action": "information_reply",
                "event_judgment": "not_risk_event",
            },
        ]
        preds = [
            {
                "risk_level": "high_risk",
                "recommended_action": "emergency_review",
                "event_judgment": "risk_event",
            },
            {
                "risk_level": "low_risk",
                "recommended_action": "information_reply",
                "event_judgment": "not_risk_event",
            },
        ]
        metas = [{"topic": "动力电池与热安全"}, {"topic": "无风险事件"}]
        result = eval_multi_field(targets, preds, metas)
        assert result["risk_per_topic_acc"]["动力电池与热安全"] == 1.0
        assert result["risk_per_topic_acc"]["无风险事件"] == 1.0
        assert result["emergency_review_fpr"] == 0.0

    def test_emergency_fpr(self):
        targets = [
            {
                "risk_level": "low_risk",
                "recommended_action": "information_reply",
                "event_judgment": "not_risk_event",
            },
            {
                "risk_level": "mid_risk",
                "recommended_action": "service_followup",
                "event_judgment": "risk_event",
            },
        ]
        preds = [
            {
                "risk_level": "high_risk",
                "recommended_action": "emergency_review",
                "event_judgment": "risk_event",
            },
            {
                "risk_level": "mid_risk",
                "recommended_action": "service_followup",
                "event_judgment": "risk_event",
            },
        ]
        result = eval_multi_field(targets, preds)
        assert result["emergency_review_fpr"] == 0.5

    def test_legacy_field_names(self):
        targets = [
            {"risk_level": "high_risk", "handling_suggestion": "ban_account", "final_judgment": "exist_violation"},
        ]
        preds = [
            {"risk_level": "high_risk", "handling_suggestion": "ban_account", "final_judgment": "exist_violation"},
        ]
        result = eval_multi_field(targets, preds)
        assert "handling_macro_f1" in result
        assert "emergency_review_fpr" in result


class TestAuprc:
    def test_perfect(self):
        assert auprc([1, 1, 0], [0.9, 0.8, 0.1]) == pytest.approx(1.0)

    def test_empty(self):
        assert auprc([], []) == 0.0


class TestFleissKappa:
    def test_perfect_agreement(self):
        matrix = [[3, 0, 0], [0, 3, 0], [0, 0, 3]]
        assert fleiss_kappa(matrix) == pytest.approx(1.0)

    def test_rejects_ragged(self):
        with pytest.raises(ValueError, match="ragged"):
            fleiss_kappa([[3, 0, 0], [2, 0, 0]])


class TestKrippendorff:
    def test_basic(self):
        annotations = [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
        assert ordinal_krippendorff_alpha(annotations) == pytest.approx(1.0)
